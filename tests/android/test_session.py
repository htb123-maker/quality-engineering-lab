"""Android Appium session smoke tests."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import shutil
import subprocess

import allure
import httpx
import pytest
from qa_core.config.settings import Settings
from qa_core.driver.android import create_android_driver


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


@allure.epic("Quality Engineering Lab")
@allure.feature("Android Appium")
@allure.story("Session lifecycle")
@pytest.mark.android
@pytest.mark.smoke
@pytest.mark.timeout(120)
@allure.testcase("SMOKE-ANDROID-SESSION-001", "Android session lifecycle")
@allure.link("docs/runbooks/failed-quality-gate.md", name="Failure triage runbook")
def test_android_session_starts_and_quits(
    settings: Settings,
    require_android_smoke_prerequisites: None,
) -> None:
    del require_android_smoke_prerequisites
    driver = create_android_driver(settings)

    try:
        assert driver.session_id
        assert driver.current_package == settings.android_app_package

        window_size = driver.get_window_size()
        assert window_size["width"] > 0
        assert window_size["height"] > 0
    finally:
        driver.quit()
