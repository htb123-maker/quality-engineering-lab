"""Fixtures for API-backed Android and iOS cross-layer E2E tests."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory, NamespaceFactory
from qa_core.db import DatabaseClient
from qa_core.driver.ios import create_ios_driver
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.android import AndroidFixtureAdapter
from qa_core.platforms.ios import IosFixtureAdapter
from qa_core.resilience import ToxiproxyClient
from qa_core.resource_pools import NamespaceLease, NamespacePool
from qa_core.security import MemberApiFactory

from tests.android.conftest import (
    FIXTURE_ACTIVITY,
    FIXTURE_PACKAGE,
    create_android_test_session,
)
from tests.cross_platform.conftest import (
    _appium_is_ready,
    _require_android_fixture,
)
from tests.ios.fixture import ios_runtime_is_configured

_RUN_ID = (os.environ.get("PYTEST_XDIST_TESTRUNUID") or uuid4().hex)[:8]


def _worker_id() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "local")


def _unique_client_id(tag: str) -> str:
    return f"week23-{_worker_id()}-{tag}-{uuid4().hex[:12]}"


@pytest.fixture(scope="session")
def database(settings: Settings) -> Iterator[DatabaseClient]:
    with DatabaseClient.from_settings(settings) as client:
        yield client


@pytest.fixture(scope="session")
def namespace_factory(database: DatabaseClient) -> NamespaceFactory:
    return NamespaceFactory(database, run_token=_RUN_ID)


@pytest.fixture(scope="session")
def namespace_pool(
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> Iterator[NamespacePool]:
    pool = NamespacePool(
        namespace_factory,
        worker_id=_worker_id(),
        run_id=_RUN_ID,
        redis_url=str(settings.redis_url),
    )
    pool.purge_stale()
    try:
        yield pool
    finally:
        pool.close()


@pytest.fixture
def namespace(namespace_pool: NamespacePool) -> Iterator[NamespaceLease]:
    with namespace_pool.lease("week23") as lease:
        yield lease


@pytest.fixture
def owner_auth(namespace: NamespaceLease, settings: Settings) -> Iterator[AuthClient]:
    with AuthClient.from_settings(settings) as auth:
        auth.login(namespace.owner_email, settings.auth_test_password)
        yield auth


@pytest.fixture
def catalog_items(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> Iterator[CatalogApiFactory]:
    factory = CatalogApiFactory(
        auth=owner_auth,
        workspace_slug=namespace.slug,
        client_id=_unique_client_id("catalog"),
    )
    try:
        yield factory
    finally:
        factory.cleanup()


@contextmanager
def role_auth(
    *,
    role: str,
    namespace: NamespaceLease,
    owner_auth: AuthClient,
    settings: Settings,
) -> Iterator[AuthClient]:
    """Return a real authenticated session for one role."""

    if role == "owner":
        yield owner_auth
        return
    if role == "viewer":
        assert namespace.viewer_email is not None
        with AuthClient.from_settings(settings) as auth:
            auth.login(namespace.viewer_email, settings.auth_test_password)
            yield auth
        return
    member = MemberApiFactory(
        owner_auth,
        namespace.slug,
        client_id=_unique_client_id,
    ).invite(role)
    with AuthClient.from_settings(settings) as auth:
        auth.login(member.email, settings.auth_test_password)
        yield auth


@pytest.fixture(scope="session")
def android_e2e_adapter(
    settings: Settings,
    project_root: Path,
) -> Iterator[AndroidFixtureAdapter]:
    _require_android_fixture(settings)
    api_port = urlparse(str(settings.api_base_url)).port or 18000
    adb = "adb"
    reverse_result = subprocess.run(
        [
            adb,
            "-s",
            settings.android_udid,
            "reverse",
            f"tcp:{api_port}",
            f"tcp:{api_port}",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if reverse_result.returncode != 0:
        raise RuntimeError(
            "adb reverse failed: "
            f"{reverse_result.stderr.strip() or reverse_result.stdout.strip()}"
        )
    driver = create_android_test_session(
        settings,
        package=FIXTURE_PACKAGE,
        activity=FIXTURE_ACTIVITY,
    )
    adapter = AndroidFixtureAdapter(
        driver,
        component=f"{FIXTURE_PACKAGE}/{FIXTURE_ACTIVITY}",
        wait_policy=WaitPolicy(
            timeout_seconds=settings.android_ui_wait_timeout_seconds,
            poll_interval_seconds=settings.android_ui_wait_poll_seconds,
        ),
        diagnostics_directory=project_root / "artifacts" / "e2e" / "week23" / "android",
    )
    try:
        yield adapter
    finally:
        adapter.files.cleanup()
        driver.quit()
        subprocess.run(
            [
                adb,
                "-s",
                settings.android_udid,
                "reverse",
                "--remove",
                f"tcp:{api_port}",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )


@pytest.fixture(scope="session")
def ios_e2e_adapter(
    settings: Settings,
    project_root: Path,
) -> Iterator[IosFixtureAdapter]:
    if not ios_runtime_is_configured():
        pytest.skip("iOS E2E requires macOS or a cloud provider.")
    if not _appium_is_ready(settings):
        pytest.skip("iOS E2E requires a ready Appium server.")
    bundle_id = "com.example.qaweek19"
    driver: WebDriver = create_ios_driver(
        settings.model_copy(update={"ios_bundle_id": bundle_id})
    )
    adapter = IosFixtureAdapter(
        driver,
        bundle_id=bundle_id,
        wait_policy=WaitPolicy(timeout_seconds=60.0, poll_interval_seconds=0.5),
        diagnostics_directory=project_root / "artifacts" / "e2e" / "week23" / "ios",
    )
    try:
        yield adapter
    finally:
        adapter.files.cleanup()
        driver.quit()


@pytest.fixture(scope="session")
def toxiproxy(settings: Settings) -> Iterator[ToxiproxyClient]:
    """Return the optional Toxiproxy control client for recovery tests."""

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
def e2e_fault_proxy(
    toxiproxy: ToxiproxyClient,
    settings: Settings,
) -> Iterator[tuple[ToxiproxyClient, str, str]]:
    """Yield a Week 24 worker-specific API proxy and host base URL."""

    worker = _worker_id()
    worker_index = int(worker.removeprefix("gw")) if worker.startswith("gw") else 0
    port = settings.toxiproxy_proxy_port_base + worker_index
    name = f"qa-week24-{worker}"
    proxy = toxiproxy.ensure_proxy(
        name=name,
        listen=f"0.0.0.0:{port}",
        upstream="api:8000",
    )
    try:
        yield toxiproxy, proxy.name, f"http://127.0.0.1:{port}"
    finally:
        toxiproxy.delete_proxy(proxy.name)
