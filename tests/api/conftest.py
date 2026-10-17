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
import httpx
import pytest
from qa_core.auth import AuthClient
from qa_core.cache import CatalogCacheProbe
from qa_core.config.settings import Settings
from qa_core.data_factories import (
    CatalogApiFactory,
    NamespaceFactory,
    item_path,
    items_path,
)
from qa_core.db import DatabaseClient
from qa_core.events import WebSocketConnection, events_url
from qa_core.jobs import JobClient
from qa_core.resilience import ToxiproxyClient
from qa_core.resource_pools import NamespaceLease, NamespacePool
from qa_core.security import (
    MemberApiFactory,
    SignInThrottleProbe,
    member_path,
    members_path,
)

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
    "AuthClient",
    "attach_json",
    "connect_event_stream",
    "item_path",
    "items_path",
    "member_path",
    "members_path",
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


def connect_event_stream(
    sut_api_url: str,
    workspace_slug: str,
    access_token: str,
    *,
    timeout: float = 5.0,
) -> WebSocketConnection:
    """Open an authenticated WebSocket event stream for one workspace."""

    return WebSocketConnection.connect(
        events_url(sut_api_url, workspace_slug),
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=timeout,
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


@pytest.fixture
def job_client(owner_auth: AuthClient) -> JobClient:
    """Return a background job client bound to the leased namespace owner."""

    return JobClient.from_auth(owner_auth)


@pytest.fixture
def owner_access_token(owner_auth: AuthClient) -> str:
    """Return the raw access token so a WebSocket handshake can send it."""

    tokens = owner_auth.tokens
    assert tokens is not None, "owner_auth must log in before reading its token"
    return tokens.access_token


@pytest.fixture
def member_api(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> MemberApiFactory:
    """Return a member factory bound to the leased namespace owner."""

    return MemberApiFactory(owner_auth, namespace.slug)


@pytest.fixture
def role_sessions(
    owner_auth: AuthClient,
    member_api: MemberApiFactory,
    settings: Settings,
) -> Iterator[dict[str, AuthClient]]:
    """Log in one member per role so RBAC tests can compare all four.

    The owner session comes from ``owner_auth``; admin, member, and viewer are
    invited through the members API and then authenticated with the shared test
    password, which is how the SUT seeds every account.
    """

    sessions: dict[str, AuthClient] = {"owner": owner_auth}
    try:
        for role in ("admin", "member", "viewer"):
            identity = member_api.invite(role)
            auth = AuthClient.from_settings(settings)
            auth.login(identity.email, settings.auth_test_password)
            sessions[role] = auth
        yield sessions
    finally:
        for role, session in sessions.items():
            if role != "owner":
                session.close()


@pytest.fixture
def signin_throttle(settings: Settings) -> Iterator[SignInThrottleProbe]:
    """Return a probe for the SUT's failed sign-in counter."""

    probe = SignInThrottleProbe(str(settings.redis_url))
    try:
        yield probe
    finally:
        probe.close()


@pytest.fixture
def catalog_cache(settings: Settings, namespace: NamespaceLease) -> Iterator[CatalogCacheProbe]:
    """Return a cache probe for the leased namespace, cleaned afterwards."""

    probe = CatalogCacheProbe(
        redis_url=str(settings.redis_url),
        workspace_slug=namespace.slug,
    )
    probe.purge()
    try:
        yield probe
    finally:
        probe.purge()


@pytest.fixture(scope="session")
def toxiproxy(settings: Settings) -> Iterator[ToxiproxyClient]:
    """Return the optional fault-injection control client."""

    client = ToxiproxyClient(
        str(settings.toxiproxy_url),
        timeout=settings.toxiproxy_timeout_seconds,
    )
    try:
        client.list_proxies()
    except (httpx.HTTPError, ValueError) as exc:
        client.close()
        pytest.skip(f"Toxiproxy is not running: {type(exc).__name__}: {exc}")
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def fault_proxy(
    toxiproxy: ToxiproxyClient,
    settings: Settings,
) -> Iterator[tuple[ToxiproxyClient, str, str]]:
    """Yield a worker-specific API proxy and its host-side base URL."""

    worker = worker_id()
    worker_index = int(worker.removeprefix("gw")) if worker.startswith("gw") else 0
    port = settings.toxiproxy_proxy_port_base + worker_index
    name = f"qa-week12-{worker}"
    proxy = toxiproxy.ensure_proxy(
        name=name,
        listen=f"0.0.0.0:{port}",
        upstream="api:8000",
    )
    try:
        yield toxiproxy, proxy.name, f"http://127.0.0.1:{port}"
    finally:
        toxiproxy.delete_proxy(proxy.name)
