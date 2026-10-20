"""Shared Android device-matrix, session, and diagnostics fixtures."""

import json
import shutil
import subprocess
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any, cast

import allure
import httpx
import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.driver.android import create_android_driver
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.android import AndroidActivities, AndroidIntent
from qa_core.platforms.android.devices import (
    AndroidDeviceProfile,
    load_android_device_matrix,
    select_worker_device,
    xdist_worker_context,
)

FIXTURE_PACKAGE = "com.example.qaweek15"
FIXTURE_ACTIVITY = ".MainActivity"
_ANDROID_DRIVER_KEY: pytest.StashKey[WebDriver] = pytest.StashKey()
_ANDROID_PROFILE_KEY: pytest.StashKey[AndroidDeviceProfile] = pytest.StashKey()


def create_android_test_session(
    settings: Settings,
    *,
    package: str,
    activity: str,
) -> WebDriver:
    """Create a session and force the intended test component into the foreground."""

    target = settings.model_copy(
        update={
            "android_app_package": package,
            "android_app_activity": activity,
        }
    )
    driver = create_android_driver(target)
    try:
        activities = AndroidActivities(
            driver,
            WaitPolicy(
                timeout_seconds=settings.android_ui_wait_timeout_seconds,
                poll_interval_seconds=settings.android_ui_wait_poll_seconds,
            ),
        )
        activities.start(
            AndroidIntent(
                action="android.intent.action.MAIN",
                component=f"{package}/{activity}",
                stop=True,
            )
        )
    except Exception:
        driver.quit()
        raise
    return driver


@pytest.fixture(scope="session")
def android_device_profiles(
    settings: Settings,
    project_root: Path,
) -> tuple[AndroidDeviceProfile, ...]:
    """Load the active device matrix for this test process."""

    matrix_path = settings.android_device_matrix
    if not matrix_path.is_absolute():
        matrix_path = project_root / matrix_path
    return load_android_device_matrix(matrix_path)


@pytest.fixture(scope="session")
def android_worker_profile(
    android_device_profiles: tuple[AndroidDeviceProfile, ...],
) -> AndroidDeviceProfile:
    """Bind the current serial or xdist worker to one matrix device."""

    worker_index, worker_count = xdist_worker_context()
    return select_worker_device(
        android_device_profiles,
        f"gw{worker_index}",
        worker_count,
    )


@pytest.fixture(scope="session")
def android_settings(
    settings: Settings,
    android_worker_profile: AndroidDeviceProfile,
) -> Settings:
    """Return settings targeting the device assigned to this worker."""

    updates: dict[str, object] = {
        "android_udid": android_worker_profile.udid,
        "android_device_name": android_worker_profile.device_id,
    }
    if android_worker_profile.platform_version:
        updates["android_platform_version"] = android_worker_profile.platform_version
    return settings.model_copy(update=updates)


@pytest.fixture(autouse=True)
def attach_android_device_context(
    request: pytest.FixtureRequest,
    android_worker_profile: AndroidDeviceProfile,
) -> Iterator[None]:
    """Attach the assigned device to every Allure result in this suite."""

    allure.dynamic.parameter("android_device", android_worker_profile.device_id)
    allure.dynamic.parameter("android_udid", android_worker_profile.udid)
    allure.dynamic.parameter("android_role", android_worker_profile.role)
    request.node.stash[_ANDROID_PROFILE_KEY] = android_worker_profile
    yield


@pytest.fixture(scope="session")
def require_android_smoke_prerequisites(
    request: pytest.FixtureRequest,
    android_settings: Settings,
    android_worker_profile: AndroidDeviceProfile,
) -> None:
    """Skip with an exact reason when ADB or Appium is not ready."""

    request.node.stash[_ANDROID_PROFILE_KEY] = android_worker_profile
    adb = shutil.which("adb")
    if adb is None:
        pytest.skip("Android smoke requires adb on PATH.")

    try:
        adb_result = subprocess.run(
            [adb, "-s", android_settings.android_udid, "get-state"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(
            f"Android smoke could not query {android_settings.android_udid}: {exc}"
        )

    adb_state = adb_result.stdout.strip()
    if adb_result.returncode != 0 or adb_state != "device":
        detail = adb_result.stderr.strip() or adb_result.stdout.strip() or "no output"
        pytest.skip(
            f"Android smoke requires {android_settings.android_udid} in state "
            f"'device': {detail}"
        )

    appium_status_url = (
        f"{str(android_settings.appium_server_url).rstrip('/')}/status"
    )
    try:
        appium_response = httpx.get(appium_status_url, timeout=3)
        appium_response.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"Android smoke requires a ready Appium server: {exc}")

    status_payload = appium_response.json()
    status_value = status_payload.get("value", status_payload)
    if not status_value.get("ready"):
        pytest.skip(f"Android smoke requires Appium ready=true: {status_payload}")


@pytest.fixture
def android_driver(
    request: pytest.FixtureRequest,
    android_settings: Settings,
    android_worker_profile: AndroidDeviceProfile,
    require_android_smoke_prerequisites: None,
) -> Iterator[WebDriver]:
    """Create and always clean up one Android Appium session."""

    del require_android_smoke_prerequisites
    driver = create_android_test_session(
        android_settings,
        package=android_settings.android_app_package,
        activity=android_settings.android_app_activity,
    )
    request.node.stash[_ANDROID_DRIVER_KEY] = driver
    request.node.stash[_ANDROID_PROFILE_KEY] = android_worker_profile
    try:
        yield driver
    finally:
        driver.quit()


@pytest.fixture
def android_fixture_driver(
    request: pytest.FixtureRequest,
    android_settings: Settings,
    android_worker_profile: AndroidDeviceProfile,
    require_android_smoke_prerequisites: None,
) -> Iterator[WebDriver]:
    """Create one session against the installed Android fixture."""

    del require_android_smoke_prerequisites
    adb = shutil.which("adb")
    if adb is None:
        pytest.skip("Android fixture requires adb on PATH.")
    package_result = subprocess.run(
        [
            adb,
            "-s",
            android_settings.android_udid,
            "shell",
            "pm",
            "path",
            FIXTURE_PACKAGE,
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )
    if package_result.returncode != 0 or not package_result.stdout.startswith("package:"):
        pytest.skip(
            f"Android fixture is not installed on {android_settings.android_udid}; "
            "run .\\scripts\\run_android_matrix.ps1."
        )

    driver = create_android_test_session(
        android_settings,
        package=FIXTURE_PACKAGE,
        activity=FIXTURE_ACTIVITY,
    )
    request.node.stash[_ANDROID_DRIVER_KEY] = driver
    request.node.stash[_ANDROID_PROFILE_KEY] = android_worker_profile
    try:
        yield driver
    finally:
        driver.quit()


@pytest.fixture(scope="session")
def android_fixture_session(
    request: pytest.FixtureRequest,
    android_settings: Settings,
    android_worker_profile: AndroidDeviceProfile,
    require_android_smoke_prerequisites: None,
) -> Iterator[WebDriver]:
    """Create one long-lived fixture session per xdist worker and device."""

    del require_android_smoke_prerequisites
    adb = shutil.which("adb")
    if adb is None:
        pytest.skip("Android fixture requires adb on PATH.")
    package_result = subprocess.run(
        [
            adb,
            "-s",
            android_settings.android_udid,
            "shell",
            "pm",
            "path",
            FIXTURE_PACKAGE,
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )
    if package_result.returncode != 0 or not package_result.stdout.startswith("package:"):
        pytest.skip(
            f"Android fixture is not installed on {android_settings.android_udid}; "
            "run .\\scripts\\run_android_matrix.ps1."
        )

    driver = create_android_test_session(
        android_settings,
        package=FIXTURE_PACKAGE,
        activity=FIXTURE_ACTIVITY,
    )
    request.node.stash[_ANDROID_DRIVER_KEY] = driver
    request.node.stash[_ANDROID_PROFILE_KEY] = android_worker_profile
    try:
        yield driver
    finally:
        driver.quit()


@pytest.fixture
def android_fixture_device(
    request: pytest.FixtureRequest,
    android_fixture_session: WebDriver,
    android_worker_profile: AndroidDeviceProfile,
) -> Iterator[WebDriver]:
    """Expose the worker session and register it for failure diagnostics."""

    request.node.stash[_ANDROID_DRIVER_KEY] = android_fixture_session
    request.node.stash[_ANDROID_PROFILE_KEY] = android_worker_profile
    yield android_fixture_session


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[None],
) -> Generator[None, object, None]:
    """Attach Android failure evidence without changing test outcomes."""

    outcome = yield
    report = cast(Any, outcome).get_result()
    if call.when != "call" or not report.failed or item.get_closest_marker("android") is None:
        return

    driver = item.stash.get(_ANDROID_DRIVER_KEY, None)
    profile = item.stash.get(_ANDROID_PROFILE_KEY, None)
    if driver is None or profile is None:
        return

    try:
        allure.attach(
            driver.get_screenshot_as_png(),
            name=f"{profile.device_id}-failure",
            attachment_type=allure.attachment_type.PNG,
        )
    except Exception as exc:
        allure.attach(
            f"screenshot unavailable: {type(exc).__name__}: {exc}",
            name=f"{profile.device_id}-screenshot-error",
            attachment_type=allure.attachment_type.TEXT,
        )

    try:
        allure.attach(
            driver.page_source,
            name=f"{profile.device_id}-page-source",
            attachment_type=allure.attachment_type.XML,
        )
    except Exception as exc:
        allure.attach(
            f"page source unavailable: {type(exc).__name__}: {exc}",
            name=f"{profile.device_id}-page-source-error",
            attachment_type=allure.attachment_type.TEXT,
        )

    adb = shutil.which("adb")
    if adb is None:
        return
    try:
        logcat = subprocess.run(
            [adb, "-s", profile.udid, "logcat", "-d", "-t", "1000"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        ).stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        logcat = f"logcat unavailable: {type(exc).__name__}: {exc}"
    allure.attach(
        logcat or "logcat returned no output",
        name=f"{profile.device_id}-logcat",
        attachment_type=allure.attachment_type.TEXT,
    )


def attach_android_device_metadata(profile: AndroidDeviceProfile) -> None:
    """Attach a stable JSON description of the assigned device."""

    payload: dict[str, Any] = {
        "device_id": profile.device_id,
        "role": profile.role,
        "udid": profile.udid,
        "platform_version": profile.platform_version,
        "required": profile.required,
    }
    allure.attach(
        json.dumps(payload, indent=2, sort_keys=True),
        name=f"{profile.device_id}-metadata",
        attachment_type=allure.attachment_type.JSON,
    )
