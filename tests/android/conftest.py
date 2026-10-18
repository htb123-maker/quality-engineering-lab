"""Shared Android environment checks."""

import shutil
import subprocess

import httpx
import pytest
from qa_core.config.settings import Settings


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
