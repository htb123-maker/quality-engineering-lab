"""Small synchronous PostgreSQL client for test data setup and cleanup."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from types import TracebackType
from typing import Any, Self

import psycopg
from psycopg import Connection, Transaction
from psycopg.rows import dict_row

from qa_core.config.settings import Settings

Params = Sequence[Any] | Mapping[str, Any]


class DatabaseClient:
    """Run seeding, reads, and idempotent deletes against the test schema.

    Statements run in autocommit mode because Week 8 needs nothing more than
    deterministic setup and repeatable cleanup. Transaction, isolation-level,
    and lock experiments belong to the Week 9 database plan and build on
    :meth:`transaction`.
    """

    def __init__(self, dsn: str, *, connect_timeout: int = 5) -> None:
        self._connection: Connection[dict[str, Any]] = psycopg.connect(
            dsn,
            connect_timeout=connect_timeout,
            autocommit=True,
            row_factory=dict_row,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Open a client for the configured test database."""

        return cls(str(settings.postgres_dsn))

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
