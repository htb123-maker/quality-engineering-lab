"""Week 19 real-iOS fixture acceptance cases."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import allure
import pytest
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver
from qa_core.platforms.ios import (
    IosAlertAction,
    IosDiagnostics,
)
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from tests.ios.fixture import (
    DEEP_LINK,
    FixtureScreen,
    handle_optional_permission_prompt,
    handle_permission_prompt,
    relaunch_fixture,
)
from tests.ios.fixture import (
    open_fixture as _open_fixture,
)
from tests.ios.fixture import (
    reset_permission as _reset_permission,
)

CLOUD_PROVIDERS = {"browserstack", "saucelabs", "lambdatest"}


pytestmark = [
    pytest.mark.ios,
    pytest.mark.smoke,
    pytest.mark.timeout(900),
    pytest.mark.skipif(
        os.getenv("QA_IOS_DEVICE_PROVIDER", "local").lower()
        not in CLOUD_PROVIDERS
        and sys.platform != "darwin",
        reason="Week 19 iOS fixture requires macOS or a cloud provider.",
    ),
]


def _capture_step(
    diagnostics: IosDiagnostics,
    step: str,
    *,
    feature: str = "Fixture state",
) -> None:
    try:
        capture = diagnostics.capture(step)
    except Exception as exc:
        allure.attach(
            f"{type(exc).__name__}: {exc}",
            name=f"Diagnostics failed: {step}",
            attachment_type=allure.attachment_type.TEXT,
        )
        return
    allure.attach.file(
        str(capture.screenshot_path),
        name=f"{feature} screenshot: {step}",
        attachment_type=allure.attachment_type.PNG,
    )
    allure.attach.file(
        str(capture.page_source_path),
        name=f"{feature} page source: {step}",
        attachment_type=allure.attachment_type.XML,
    )


@pytest.fixture
def ios_driver(settings: Settings, request: pytest.FixtureRequest) -> Iterator[Any]:
    """Create one isolated cloud or simulator session per acceptance case."""

    driver = create_ios_driver(settings)
    diagnostics = IosDiagnostics(
        driver,
        Path("artifacts/ios-diagnostics") / request.node.name,
    )
    try:
        yield driver
    except Exception:
        _capture_step(diagnostics, "failure", feature=request.node.name)
        raise
    finally:
        _capture_step(diagnostics, "final", feature=request.node.name)
        driver.quit()


def _relaunch_fixture(driver: Any, settings: Settings) -> None:
    relaunch_fixture(driver, settings.ios_bundle_id)


def _handle_permission_prompt(
    driver: Any,
    action: IosAlertAction,
    *,
    timeout_seconds: float = 15.0,
) -> None:
    handle_permission_prompt(
        driver,
        action,
        timeout_seconds=timeout_seconds,
    )


def _handle_optional_permission_prompt(driver: Any) -> bool:
    return handle_optional_permission_prompt(driver)


@allure.feature("iOS System Interactions")
@allure.story("Week 19 fixture")
def test_01_fixture_launches(ios_driver: Any) -> None:
    screen, _ = _open_fixture(ios_driver)

    assert screen.element().is_displayed()


def test_02_camera_permission_can_be_granted(ios_driver: Any, settings: Settings) -> None:
    _reset_permission(ios_driver, "camera")
    _relaunch_fixture(ios_driver, settings)
    screen, wait = _open_fixture(ios_driver)

    wait.text_is(screen.scope(), FixtureScreen.camera_status, "camera: not-determined")
    screen.tap(FixtureScreen.camera_button)
    _handle_permission_prompt(ios_driver, IosAlertAction.ACCEPT)
    wait.text_is(screen.scope(), FixtureScreen.camera_status, "camera: granted")


def test_03_microphone_permission_can_be_denied(
    ios_driver: Any,
    settings: Settings,
) -> None:
    _reset_permission(ios_driver, "microphone")
    _relaunch_fixture(ios_driver, settings)
    screen, wait = _open_fixture(ios_driver)

    wait.text_is(
        screen.scope(),
        FixtureScreen.microphone_status,
        "microphone: not-determined",
    )
    screen.tap(FixtureScreen.microphone_button)
    _handle_permission_prompt(ios_driver, IosAlertAction.DISMISS)
    wait.text_is(
        screen.scope(),
        FixtureScreen.microphone_status,
        "microphone: denied",
    )


def test_04_permission_state_survives_relaunch(
    ios_driver: Any,
    settings: Settings,
) -> None:
    _reset_permission(ios_driver, "camera")
    _relaunch_fixture(ios_driver, settings)
    screen, wait = _open_fixture(ios_driver)
    screen.tap(FixtureScreen.camera_button)
    _handle_permission_prompt(ios_driver, IosAlertAction.ACCEPT)
    wait.text_is(screen.scope(), FixtureScreen.camera_status, "camera: granted")

    _relaunch_fixture(ios_driver, settings)
    screen, wait = _open_fixture(ios_driver)
    wait.text_is(screen.scope(), FixtureScreen.camera_status, "camera: granted")


def test_05_notification_authorization_and_scheduling(ios_driver: Any) -> None:
    screen, wait = _open_fixture(ios_driver)

    screen.tap(FixtureScreen.notification_button)
    _handle_optional_permission_prompt(ios_driver)
    wait.text_is(
        screen.scope(),
        FixtureScreen.notification_status,
        "notifications: authorized",
    )
    screen.tap(FixtureScreen.send_notification_button)
    wait.text_is(
        screen.scope(),
        FixtureScreen.notification_status,
        "notifications: scheduled",
    )


def test_06_in_app_deep_link_opens(ios_driver: Any) -> None:
    screen, wait = _open_fixture(ios_driver)

    screen.tap(FixtureScreen.deep_link_button)
    wait.text_is(
        screen.scope(),
        FixtureScreen.deep_link_status,
        "deep link: opened qaweek19://system-interactions?case=deep-link",
    )


def test_07_external_cold_start_deep_link_opens(
    ios_driver: Any,
    settings: Settings,
) -> None:
    _open_fixture(ios_driver)
    ios_driver.terminate_app(settings.ios_bundle_id)

    ios_driver.execute_script(
        "mobile: deepLink",
        {"url": DEEP_LINK, "bundleId": settings.ios_bundle_id},
    )
    screen, wait = _open_fixture(ios_driver)

    wait.text_is(
        screen.scope(),
        FixtureScreen.deep_link_status,
        f"deep link: opened {DEEP_LINK}",
    )


def test_08_file_write_and_read(ios_driver: Any) -> None:
    screen, wait = _open_fixture(ios_driver)

    screen.tap(FixtureScreen.write_file_button)
    wait.text_is(screen.scope(), FixtureScreen.file_status, "file: written")
    screen.tap(FixtureScreen.read_file_button)
    wait.text_is(
        screen.scope(),
        FixtureScreen.file_status,
        "file: read week19-file",
    )


def test_09_webview_context_is_available(
    ios_driver: Any,
    settings: Settings,
) -> None:
    screen, wait = _open_fixture(ios_driver)
    timeout_seconds = settings.ios_webview_connect_timeout_ms / 1000 + 10

    try:
        webview_context = WebDriverWait(
            ios_driver,
            timeout=timeout_seconds,
            poll_frequency=1.0,
        ).until(
            lambda driver: next(
                (
                    context
                    for context in driver.contexts
                    if "WEBVIEW" in context.upper()
                ),
                None,
            )
        )
    except TimeoutException:
        pytest.xfail(
            "BrowserStack real iPhone exposes only "
            f"{ios_driver.contexts!r} after {timeout_seconds:.0f}s"
        )
    ios_driver.switch_to.context(webview_context)
    web_status = WebDriverWait(ios_driver, timeout=20).until(
        lambda driver: driver.find_element("css selector", "#web-status")
    )
    assert web_status.text == "ready"
    ios_driver.execute_script(
        "document.getElementById('web-accept').click();"
        "return document.getElementById('web-status').textContent;"
    )

    ios_driver.switch_to.context("NATIVE_APP")
    screen, wait = _open_fixture(ios_driver)
    assert screen.element().is_displayed()
    allure.attach(
        webview_context,
        name="WebView context",
        attachment_type=allure.attachment_type.TEXT,
    )


def test_10_background_and_foreground_recovery(ios_driver: Any) -> None:
    _open_fixture(ios_driver)

    ios_driver.background_app(1)
    WebDriverWait(ios_driver, timeout=20, poll_frequency=0.5).until(
        lambda driver: driver.find_element(
            *FixtureScreen.background_status.as_tuple()
        ).text.startswith("background: resumed")
    )
