"""Fixtures for database-focused integration tests.

These tests need more than one connection: a holder, a waiter, and often a
watcher. :class:`ConnectionFactory` hands them out and always rolls back and
closes them afterwards, so a test that fails halfway cannot leave a session
holding a row lock for the rest of the suite.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from qa_core.config.settings import Settings
from qa_core.data_factories import NamespaceFactory, NamespaceIdentity
from qa_core.db import DatabaseClient, IsolationLevelName

_RUN_ID = (os.environ.get("PYTEST_XDIST_TESTRUNUID") or uuid4().hex)[:8]


class ConnectionFactory:
    """Open throwaway connections that are rolled back and closed at teardown."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients: list[DatabaseClient] = []

    def open(
        self,
        *,
        autocommit: bool = False,
        isolation_level: IsolationLevelName | None = None,
        application_name: str | None = None,
    ) -> DatabaseClient:
        """Open one extra connection and remember it for cleanup."""

        client = DatabaseClient.from_settings(
            self._settings,
            autocommit=autocommit,
            isolation_level=isolation_level,
            application_name=application_name or "qa-week9",
        )
        self._clients.append(client)
        return client

    def close(self) -> None:
        """Roll back, then close every connection this factory opened."""

        while self._clients:
            client = self._clients.pop()
            try:
                client.rollback()
            except Exception:  # a broken connection still has to be closed
                pass
            client.close()


@dataclass(frozen=True)
class BulkCatalog:
    """A larger catalog volume used for planner and index evidence."""

    slug: str
    workspace_ids: tuple[int, ...]
    focus_workspace_id: int
    items_per_workspace: int
    active_items_in_focus: int


def run_id() -> str:
    """Return the short identifier shared by every database test of one run."""

    return _RUN_ID


@pytest.fixture(scope="session")
def database(settings: Settings) -> Iterator[DatabaseClient]:
    """Return an autocommit client for seeding, reading, and cleaning."""

    with DatabaseClient.from_settings(settings, application_name="qa-week9-main") as db:
        yield db


@pytest.fixture(scope="session")
def namespace_factory(database: DatabaseClient) -> NamespaceFactory:
    """Return the factory that seeds isolated test workspaces."""

    return NamespaceFactory(database, run_token=run_id())


@pytest.fixture
def connection_factory(settings: Settings) -> Iterator[ConnectionFactory]:
    """Return a factory for extra connections opened by one test."""

    factory = ConnectionFactory(settings)
    try:
        yield factory
    finally:
        factory.close()


@pytest.fixture
def db_namespace(
    namespace_factory: NamespaceFactory,
) -> Iterator[NamespaceIdentity]:
    """Yield a disposable namespace with two seeded catalog items."""

    identity = namespace_factory.create(tag="week9", items=2)
    try:
        yield identity
    finally:
        namespace_factory.purge(identity)


@pytest.fixture
def bulk_catalog(database: DatabaseClient) -> Iterator[BulkCatalog]:
    """Seed 200 workspaces with 100 items each so the planner prefers an index."""

    workspaces = 200
    items_per_workspace = 100
    slug = f"qa-ns-{run_id()}-bulk-{uuid4().hex[:6]}"
    try:
        rows = database.fetch_all(
            """
            INSERT INTO workspaces (slug, name)
            SELECT %s || '-w' || lpad(g::text, 4, '0'), 'Bulk ' || g
            FROM generate_series(1, %s) AS g
            RETURNING id
            """,
            (slug, workspaces),
        )
        workspace_ids = tuple(int(row["id"]) for row in rows)
        database.execute(
            """
            INSERT INTO catalog_items (workspace_id, sku, name, price_cents, status)
            SELECT w.workspace_id,
                   'BULK-' || lpad(w.workspace_id::text, 6, '0')
                       || '-' || lpad(i::text, 3, '0'),
                   'Bulk item ' || i,
                   i * 7,
                   CASE WHEN i %% 10 = 0 THEN 'archived' ELSE 'active' END
            FROM unnest(%s::bigint[]) AS w(workspace_id),
                 generate_series(1, %s) AS i
            """,
            (list(workspace_ids), items_per_workspace),
        )
        database.execute("ANALYZE catalog_items")
        yield BulkCatalog(
            slug=slug,
            workspace_ids=workspace_ids,
            focus_workspace_id=workspace_ids[0],
            items_per_workspace=items_per_workspace,
            active_items_in_focus=items_per_workspace
            - items_per_workspace // 10,
        )
    finally:
        database.execute(
            "DELETE FROM workspaces WHERE starts_with(slug, %s)",
            (slug,),
        )
