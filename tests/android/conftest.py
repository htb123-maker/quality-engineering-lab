"""Shared Android environment checks."""

import shutil
import subprocess
from collections.abc import Iterator

import httpx
import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.driver.android import create_android_driver
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.android import AndroidActivities, AndroidIntent

FIXTURE_PACKAGE = "com.example.qaweek15"
FIXTURE_ACTIVITY = ".MainActivity"


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
def require_android_smoke_prerequisites(settings: Settings) -> None:
    """Skip with an exact reason when ADB or Appium is not ready."""

    adb = shutil.which("adb")
    if adb is None:
        pytest.skip("Android smoke requires adb on PATH.")

    try:
        adb_result = subprocess.run(
            [adb, "-s", settings.android_udid, "get-state"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"Android smoke could not query {settings.android_udid}: {exc}")

    adb_state = adb_result.stdout.strip()
    if adb_result.returncode != 0 or adb_state != "device":
        detail = adb_result.stderr.strip() or adb_result.stdout.strip() or "no output"
        pytest.skip(
            f"Android smoke requires {settings.android_udid} in state 'device': {detail}"
        )

    appium_status_url = f"{str(settings.appium_server_url).rstrip('/')}/status"
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
    settings: Settings,
    require_android_smoke_prerequisites: None,
) -> Iterator[WebDriver]:
    """Create and always clean up one Android Appium session."""

    del require_android_smoke_prerequisites
    driver = create_android_test_session(
        settings,
        package=settings.android_app_package,
        activity=settings.android_app_activity,
    )
    try:
        yield driver
    finally:
        driver.quit()


@pytest.fixture
def android_fixture_driver(
    settings: Settings,
    require_android_smoke_prerequisites: None,
) -> Iterator[WebDriver]:
    """Create one session against the locally installed Week 15 fixture."""

    del require_android_smoke_prerequisites
    adb = shutil.which("adb")
    if adb is None:
        pytest.skip("Android fixture requires adb on PATH.")
    package_result = subprocess.run(
        [adb, "-s", settings.android_udid, "shell", "pm", "path", FIXTURE_PACKAGE],
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )
    if package_result.returncode != 0 or not package_result.stdout.startswith("package:"):
        pytest.skip(
            "Week 15 Android fixture is not installed; run "
            ".\\apps\\android-fixture\\build.ps1."
        )

    driver = create_android_test_session(
        settings,
        package=FIXTURE_PACKAGE,
        activity=FIXTURE_ACTIVITY,
    )
    try:
        yield driver
    finally:
        driver.quit()
