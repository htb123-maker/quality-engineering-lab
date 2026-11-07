"""Android process and ADB control-plane recovery on a real Appium session."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory
from qa_core.e2e import (
    E2eContext,
    E2eSetup,
    FaultSpec,
    FaultType,
    FixtureSessionApi,
    RecoveryContext,
    RecoveryJourney,
    RecoveryResult,
)
from qa_core.mobile.platforms import CatalogSnapshot, MobilePlatform
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.android import AndroidFixtureAdapter
from qa_core.resource_pools import NamespaceLease

from tests.android.conftest import (
    FIXTURE_ACTIVITY,
    FIXTURE_PACKAGE,
    create_android_test_session,
)
from tests.e2e.support import (
    CatalogSetupPort,
    CatalogVerificationPort,
    E2eCase,
)


def _case(test_id: str) -> E2eCase:
    return E2eCase(
        test_id=test_id,
        role="owner",
        item_state="active",
        session_state="valid",
        action="archive",
        expected_ui="archived",
        expected_api="archived",
        request_id_required=True,
    )


def _prepare_catalog(
    *,
    test_id: str,
    namespace: NamespaceLease,
    owner_auth: AuthClient,
    catalog_items: CatalogApiFactory,
    settings: Settings,
    sut_api_url: str,
    project_root: Path,
) -> tuple[E2eSetup, CatalogSetupPort]:
    e2e_context = E2eContext(
        run_id=uuid4().hex[:8],
        worker_id="week24",
        test_id=test_id,
        scenario_id="RECOVERY-ANDROID-CATALOG",
        platform=MobilePlatform.ANDROID,
        artifact_dir=project_root / "artifacts" / "e2e" / "week24" / test_id,
    )
    setup_port = CatalogSetupPort(
        factory=catalog_items,
        fixture_api=FixtureSessionApi(
            owner_auth,
            base_url=sut_api_url,
            client_id=f"week24-{test_id.lower()}",
        ),
        case=_case(test_id),
        mobile_base_url=str(settings.android_e2e_api_base_url).rstrip("/"),
        redis_url=str(settings.redis_url),
        settings_client_id=f"week24-{test_id.lower()}",
    )
    setup = setup_port.prepare(e2e_context)
    assert setup.context.run_id == e2e_context.run_id
    return setup, setup_port


def _new_recovery_adapter(
    *,
    settings: Settings,
    project_root: Path,
    test_id: str,
) -> tuple[AndroidFixtureAdapter, WebDriver]:
    recovery_settings = settings.model_copy(
        update={
            "android_system_port": 8300,
            "android_mjpeg_server_port": 7910,
        }
    )
    driver = create_android_test_session(
        recovery_settings,
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
        diagnostics_directory=(
            project_root / "artifacts" / "e2e" / "week24" / test_id / "android"
        ),
    )
    return adapter, driver


def _run_adb(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["adb", *args],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


@pytest.mark.e2e
@pytest.mark.android
@pytest.mark.recovery
@pytest.mark.timeout(900)
def test_android_process_loss_relaunches_and_catalog_recovers(
    android_e2e_adapter: AndroidFixtureAdapter,
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
    owner_auth: AuthClient,
    settings: Settings,
    sut_api_url: str,
    project_root: Path,
) -> None:
    """Force-stop the app, relaunch it, and verify the same item recovers."""

    test_id = "W24-AND-001"
    setup, _ = _prepare_catalog(
        test_id=test_id,
        namespace=namespace,
        owner_auth=owner_auth,
        catalog_items=catalog_items,
        settings=settings,
        sut_api_url=sut_api_url,
        project_root=project_root,
    )
    base_url = str(settings.android_e2e_api_base_url).rstrip("/")

    def open_catalog() -> CatalogSnapshot:
        return android_e2e_adapter.catalog.open(
            base_url=base_url,
            session_id=setup.fixture_session_id,
        )

    def force_stop_app() -> None:
        result = _run_adb(
            "-s",
            settings.android_udid,
            "shell",
            "am",
            "force-stop",
            FIXTURE_PACKAGE,
        )
        assert result.returncode == 0, result.stderr

    def observe_stopped_process() -> dict[str, object]:
        result = _run_adb(
            "-s",
            settings.android_udid,
            "shell",
            "pidof",
            FIXTURE_PACKAGE,
        )
        return {
            "returncode": result.returncode,
            "pid": result.stdout.strip(),
        }

    def relaunch_app() -> None:
        android_e2e_adapter.launch_fixture()

    def verify(snapshot: CatalogSnapshot) -> None:
        assert snapshot.item_id == setup.item_id
        assert snapshot.name == setup.item_name
        assert snapshot.status == "active"

    result = RecoveryJourney[CatalogSnapshot, dict[str, object]](
        baseline=open_catalog,
        inject=force_stop_app,
        observe=observe_stopped_process,
        remove=relaunch_app,
        probe=open_catalog,
        is_recovered=lambda snapshot: snapshot.status == "active",
        verify=verify,
    ).execute(
        RecoveryContext(
            run_id=setup.context.run_id,
            worker_id="week24",
            test_id=test_id,
            scenario_id="RECOVERY-ANDROID-PROCESS",
            platform="android",
            artifact_dir=(
                project_root / "artifacts" / "e2e" / "week24" / test_id / "android"
            ),
        ),
        FaultSpec(
            fault_type=FaultType.APP_PROCESS_LOST,
            target=FIXTURE_PACKAGE,
            expected_boundary="fixture process is absent after force-stop",
            timeout_seconds=60.0,
            cleanup_action="launch fixture again in the same Appium session",
        ),
    )

    assert result.observed["returncode"] != 0
    assert result.observed["pid"] == ""

    archived = android_e2e_adapter.catalog.archive()
    server = CatalogVerificationPort(catalog_items).verify(setup)
    assert archived.status == "archived"
    assert server.status == "archived"


@pytest.mark.e2e
@pytest.mark.android
@pytest.mark.recovery
@pytest.mark.timeout(900)
def test_android_adb_server_loss_rebuilds_session_and_catalog(
    android_e2e_adapter: AndroidFixtureAdapter,
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
    owner_auth: AuthClient,
    settings: Settings,
    sut_api_url: str,
    project_root: Path,
) -> None:
    """Stop the ADB server and rebuild an Appium session on new worker ports."""

    test_id = "W24-AND-002"
    setup, _ = _prepare_catalog(
        test_id=test_id,
        namespace=namespace,
        owner_auth=owner_auth,
        catalog_items=catalog_items,
        settings=settings,
        sut_api_url=sut_api_url,
        project_root=project_root,
    )
    base_url = str(settings.android_e2e_api_base_url).rstrip("/")
    recovered_adapter: AndroidFixtureAdapter | None = None
    recovered_driver: WebDriver | None = None

    def open_baseline() -> CatalogSnapshot:
        return android_e2e_adapter.catalog.open(
            base_url=base_url,
            session_id=setup.fixture_session_id,
        )

    def stop_adb_server() -> None:
        result = _run_adb("kill-server")
        assert result.returncode == 0, result.stderr

    def observe_adb_server_down() -> dict[str, object]:
        try:
            with socket.create_connection(("127.0.0.1", 5037), timeout=0.5):
                pass
        except OSError as exc:
            return {"listening": False, "error_type": type(exc).__name__}
        return {"listening": True, "error_type": None}

    def restore_adb_and_session() -> None:
        nonlocal recovered_adapter, recovered_driver
        start = _run_adb("start-server")
        assert start.returncode == 0, start.stderr
        wait = _run_adb("-s", settings.android_udid, "wait-for-device")
        assert wait.returncode == 0, wait.stderr
        api_port = urlparse(str(settings.android_e2e_api_base_url)).port or 18000
        reverse = _run_adb(
            "-s",
            settings.android_udid,
            "reverse",
            f"tcp:{api_port}",
            f"tcp:{api_port}",
        )
        assert reverse.returncode == 0, reverse.stderr
        recovered_adapter, recovered_driver = _new_recovery_adapter(
            settings=settings,
            project_root=project_root,
            test_id=test_id,
        )

    def probe_recovered_session() -> CatalogSnapshot:
        assert recovered_adapter is not None
        return recovered_adapter.catalog.open(
            base_url=base_url,
            session_id=setup.fixture_session_id,
        )

    def verify(snapshot: CatalogSnapshot) -> None:
        assert snapshot.item_id == setup.item_id
        assert snapshot.name == setup.item_name
        assert snapshot.status == "active"

    try:
        result: RecoveryResult[CatalogSnapshot, dict[str, object]] = (
            RecoveryJourney[CatalogSnapshot, dict[str, object]](
                baseline=open_baseline,
                inject=stop_adb_server,
                observe=observe_adb_server_down,
                remove=restore_adb_and_session,
                probe=probe_recovered_session,
                is_recovered=lambda snapshot: snapshot.status == "active",
                verify=verify,
            ).execute(
                RecoveryContext(
                    run_id=setup.context.run_id,
                    worker_id="week24",
                    test_id=test_id,
                    scenario_id="RECOVERY-ANDROID-ADB-SESSION",
                    platform="android",
                    artifact_dir=(
                        project_root
                        / "artifacts"
                        / "e2e"
                        / "week24"
                        / test_id
                        / "android"
                    ),
                ),
                FaultSpec(
                    fault_type=FaultType.ADB_TRANSPORT_LOST,
                    target=f"adb-server:{settings.android_udid}",
                    expected_boundary="ADB control port 5037 is unavailable",
                    timeout_seconds=120.0,
                    cleanup_action="restart ADB and rebuild an Appium session",
                ),
            )
        )

        assert result.observed["listening"] is False
        assert recovered_adapter is not None
        archived = recovered_adapter.catalog.archive()
        server = CatalogVerificationPort(catalog_items).verify(setup)
        assert archived.status == "archived"
        assert server.status == "archived"
    finally:
        if recovered_driver is not None:
            recovered_driver.quit()
