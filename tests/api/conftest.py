"""Fixtures for namespace-isolated API tests.

Every test that writes receives its own workspace through
:class:`qa_core.resource_pools.NamespacePool`. The pool reuses one namespace per
pytest worker and wipes it between leases, so ``xdist`` workers cannot collide
and the canonical ``atlas``/``orbit`` seed rows stay read-only.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import allure
import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import (
    CatalogApiFactory,
    NamespaceFactory,
    item_path,
    items_path,
)
from qa_core.db import DatabaseClient
from qa_core.resource_pools import NamespaceLease, NamespacePool

ATLAS_SLUG = "atlas"
ORBIT_SLUG = "orbit"
ATLAS_VIEWER_EMAIL = "viewer@atlas.example"

# One run id per pytest process. Under xdist every worker inherits the same
# PYTEST_XDIST_TESTRUNUID, so workers share a run prefix and can clean up
# leftovers from the run without touching a peer's live namespaces.
_RUN_ID = (os.environ.get("PYTEST_XDIST_TESTRUNUID") or uuid4().hex)[:8]

__all__ = [
    "ATLAS_SLUG",
    "ATLAS_VIEWER_EMAIL",
    "ORBIT_SLUG",
    "attach_json",
    "item_path",
    "items_path",
    "owner_session",
    "run_id",
    "unique_client_id",
    "worker_id",
]


def worker_id() -> str:
    """Return the pytest-xdist worker name, or ``local`` without xdist."""

    return os.environ.get("PYTEST_XDIST_WORKER", "local")


def run_id() -> str:
    """Return the short id that every worker of one run shares."""

    return _RUN_ID


def unique_client_id(tag: str) -> str:
    """Return a per-test client id so the SUT rate limiter stays isolated."""

    return f"qa8-{worker_id()}-{tag}-{uuid4().hex[:12]}"


def attach_json(name: str, payload: object) -> None:
    """Attach a JSON payload to the current Allure test."""

    allure.attach(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )


@contextmanager
def owner_session(email: str, settings: Settings) -> Iterator[AuthClient]:
    """Open an authenticated session for any seeded owner email."""

    with AuthClient.from_settings(settings) as auth:
        auth.login(email, settings.auth_test_password)
        yield auth


@pytest.fixture(scope="session")
def database(settings: Settings) -> Iterator[DatabaseClient]:
    """Return a PostgreSQL client used to seed and clean test data."""

    with DatabaseClient.from_settings(settings) as client:
        yield client


@pytest.fixture(scope="session")
def namespace_factory(database: DatabaseClient) -> NamespaceFactory:
    """Return the factory that seeds isolated test workspaces."""

    return NamespaceFactory(database, run_token=run_id())


@pytest.fixture(scope="session")
def namespace_pool(
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> Iterator[NamespacePool]:
    """Return this worker's namespace pool and clean up leftovers afterwards."""

    pool = NamespacePool(
        namespace_factory,
        worker_id=worker_id(),
        run_id=namespace_factory.run_token,
        redis_url=str(settings.redis_url),
    )
    pool.purge_stale()
    try:
        yield pool
    finally:
        pool.close()


@pytest.fixture
def namespace(namespace_pool: NamespacePool) -> Iterator[NamespaceLease]:
    """Yield this test's exclusive, empty namespace."""

    with namespace_pool.lease("case") as lease:
        yield lease


@pytest.fixture
def peer_namespace(namespace_pool: NamespacePool) -> Iterator[NamespaceLease]:
    """Yield a second, independent namespace for cross-workspace assertions."""

    with namespace_pool.lease("peer") as lease:
        yield lease


@pytest.fixture
def owner_auth(namespace: NamespaceLease, settings: Settings) -> Iterator[AuthClient]:
    """Return an owner session scoped to the leased namespace."""

    with AuthClient.from_settings(settings) as auth:
        auth.login(namespace.owner_email, settings.auth_test_password)
        yield auth


@pytest.fixture
def viewer_auth(namespace: NamespaceLease, settings: Settings) -> Iterator[AuthClient]:
    """Return a viewer session scoped to the leased namespace."""

    viewer_email = namespace.viewer_email
    assert viewer_email is not None, "lease must be created with a viewer"
    with AuthClient.from_settings(settings) as auth:
        auth.login(viewer_email, settings.auth_test_password)
        yield auth


@pytest.fixture
def atlas_owner_auth(settings: Settings) -> Iterator[AuthClient]:
    """Return an authenticated atlas owner for cross-workspace checks."""

    with AuthClient.from_settings(settings) as auth:
        auth.login(settings.auth_test_username, settings.auth_test_password)
        yield auth


@pytest.fixture
def catalog_items(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> Iterator[CatalogApiFactory]:
    """Return a catalog factory bound to the leased namespace."""

    factory = CatalogApiFactory(
        auth=owner_auth,
        workspace_slug=namespace.slug,
        client_id=unique_client_id("factory"),
    )
    try:
        yield factory
    finally:
        factory.cleanup()
