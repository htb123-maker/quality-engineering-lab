"""Platform fixtures for Week 22 cross-platform smoke tests."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.android import AndroidFixtureAdapter
from qa_core.platforms.ios import IosFixtureAdapter

from tests.android.conftest import (
    FIXTURE_ACTIVITY,
    FIXTURE_PACKAGE,
    create_android_test_session,
)
from tests.ios.fixture import ios_runtime_is_configured


def _appium_is_ready(settings: Settings) -> bool:
    url = f"{str(settings.appium_server_url).rstrip('/')}/status"
    try:
        response = httpx.get(url, timeout=3.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return False
    payload = response.json()
    value = payload.get("value", payload)
    return bool(value.get("ready"))


def _require_android_fixture(settings: Settings) -> None:
    adb = shutil.which("adb")
    if adb is None:
        pytest.skip("Android cross-platform smoke requires adb on PATH.")
    state = subprocess.run(
        [adb, "-s", settings.android_udid, "get-state"],
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )
    if state.returncode != 0 or state.stdout.strip() != "device":
        pytest.skip(
            f"Android cross-platform smoke requires {settings.android_udid} "
            "in state 'device'."
        )
    package = subprocess.run(
        [
            adb,
            "-s",
            settings.android_udid,
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
    if package.returncode != 0 or not package.stdout.startswith("package:"):
        pytest.skip(
            f"Android fixture {FIXTURE_PACKAGE} is not installed on "
            f"{settings.android_udid}."
        )
    if not _appium_is_ready(settings):
        pytest.skip("Android cross-platform smoke requires a ready Appium server.")


@pytest.fixture
def android_cross_platform_adapter(
    settings: Settings,
    project_root: Path,
) -> Iterator[AndroidFixtureAdapter]:
    """Create one UiAutomator2 adapter and always release its session."""

    _require_android_fixture(settings)
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
        diagnostics_directory=(
            project_root
            / "artifacts"
            / "cross-platform"
            / "week22"
            / settings.ios_run_id
            / "android"
        ),
    )
    try:
        yield adapter
    finally:
        adapter.files.cleanup()
        driver.quit()


@pytest.fixture
def ios_cross_platform_adapter(
    settings: Settings,
    project_root: Path,
) -> Iterator[IosFixtureAdapter]:
    """Create one XCUITest adapter for a Simulator or configured cloud run."""

    if not ios_runtime_is_configured():
        pytest.skip("iOS cross-platform smoke requires macOS or a cloud provider.")
    if not _appium_is_ready(settings):
        pytest.skip("iOS cross-platform smoke requires a ready Appium server.")

    bundle_id = "com.example.qaweek19"
    driver: WebDriver = create_ios_driver(
        settings.model_copy(update={"ios_bundle_id": bundle_id})
    )
    adapter = IosFixtureAdapter(
        driver,
        bundle_id=bundle_id,
        wait_policy=WaitPolicy(timeout_seconds=60.0, poll_interval_seconds=0.5),
        diagnostics_directory=(
            project_root
            / "artifacts"
            / "cross-platform"
            / "week22"
            / settings.ios_run_id
            / "ios"
        ),
    )
    try:
        yield adapter
    finally:
        adapter.files.cleanup()
        driver.quit()
