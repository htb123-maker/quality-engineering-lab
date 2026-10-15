"""Small synchronous PostgreSQL client for test data setup and cleanup."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from types import TracebackType
from typing import Any, Literal, Self

import psycopg
from psycopg import Connection, Transaction
from psycopg.rows import dict_row

from qa_core.config.settings import Settings

Params = Sequence[Any] | Mapping[str, Any]
IsolationLevelName = Literal[
    "read_committed",
    "repeatable_read",
    "serializable",
]

# PostgreSQL has no dirty reads; READ UNCOMMITTED behaves like READ COMMITTED,
# so only the levels with distinct observable behaviour are exposed here.
ISOLATION_LEVELS: dict[IsolationLevelName, psycopg.IsolationLevel] = {
    "read_committed": psycopg.IsolationLevel.READ_COMMITTED,
    "repeatable_read": psycopg.IsolationLevel.REPEATABLE_READ,
    "serializable": psycopg.IsolationLevel.SERIALIZABLE,
}


class DatabaseClient:
    """Run seeding, reads, and idempotent deletes against the test schema.

    Statements run in autocommit mode by default, which is all Week 8 needed for
    deterministic setup and repeatable cleanup. Week 9 needs the opposite: two
    or more concurrent sessions that hold open transactions. Pass
    ``autocommit=False`` and, when the scenario is about visibility, an explicit
    ``isolation_level``.

    Every client owns exactly one connection, so a test that needs a blocking
    pair opens two clients instead of sharing one.
    """

    def __init__(
        self,
        dsn: str,
        *,
        connect_timeout: int = 5,
        autocommit: bool = True,
        isolation_level: IsolationLevelName | None = None,
        application_name: str | None = None,
    ) -> None:
        self._connection: Connection[dict[str, Any]] = psycopg.connect(
            dsn,
            connect_timeout=connect_timeout,
            autocommit=autocommit,
            row_factory=dict_row,
            application_name=application_name,
        )
        if isolation_level is not None:
            self.set_isolation_level(isolation_level)

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        autocommit: bool = True,
        isolation_level: IsolationLevelName | None = None,
        application_name: str | None = None,
    ) -> Self:
        """Open a client for the configured test database."""

        return cls(
            str(settings.postgres_dsn),
            autocommit=autocommit,
            isolation_level=isolation_level,
            application_name=application_name,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying connection."""

        self._connection.close()

    @property
    def pid(self) -> int:
        """Return the PostgreSQL backend pid that owns this connection."""

        return int(self._connection.info.backend_pid)

    @property
    def autocommit(self) -> bool:
        """Return whether every statement is its own transaction."""

        return bool(self._connection.autocommit)

    @property
    def transaction_status(self) -> str:
        """Return ``IDLE``, ``ACTIVE``, ``INTRANS``, ``INERROR`` or ``UNKNOWN``."""

        return self._connection.info.transaction_status.name

    @property
    def isolation_level(self) -> str:
        """Return the session isolation level in lower snake case."""

        level = self._connection.isolation_level
        if level is None:
            return "default"
        return str(level.name).lower()

    def set_isolation_level(self, level: IsolationLevelName) -> None:
        """Change the session isolation level before the next transaction starts."""

        if self._connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            raise RuntimeError("cannot change isolation level inside a transaction")
        self._connection.isolation_level = ISOLATION_LEVELS[level]

    def commit(self) -> None:
        """Commit the open transaction, if any."""

        self._connection.commit()

    def rollback(self) -> None:
        """Roll back the open transaction, if any."""

        self._connection.rollback()

    def setting(self, name: str) -> str:
        """Return one session setting such as ``transaction_isolation``."""

        row = self.fetch_one("SELECT current_setting(%s) AS value", (name,))
        if row is None:
            raise RuntimeError(f"current_setting({name!r}) returned no row")
        return str(row["value"])

    def execute(self, sql: str, params: Params | None = None) -> int:
        """Run one statement and return the affected row count."""

        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount

    def fetch_all(self, sql: str, params: Params | None = None) -> list[dict[str, Any]]:
        """Run one query and return every row as a mapping."""

        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def fetch_one(
        self,
        sql: str,
        params: Params | None = None,
    ) -> dict[str, Any] | None:
        """Run one query and return the first row, if any."""

        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        """Return a transaction context for later isolation-level work."""

        with self._connection.transaction() as transaction:
            yield transaction
