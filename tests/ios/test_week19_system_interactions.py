"""Week 19 real-iOS fixture interaction smoke."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import json
import os
import sys
from pathlib import Path
from typing import Any

import allure
import pytest
from appium.webdriver.common.appiumby import AppiumBy
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver
from qa_core.mobile.screens import Screen
from qa_core.mobile.waits import MobileWait, WaitPolicy
from qa_core.platforms.ios import (
    IosAlertAction,
    IosDiagnostics,
    IosLocator,
    IosSystemAlerts,
)
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

CLOUD_PROVIDERS = {"browserstack", "saucelabs", "lambdatest"}


class FixtureScreen(Screen):
    """Stable root and controls from the Week 19 iOS fixture."""

    root_locator = IosLocator.class_chain(
        "**/XCUIElementTypeWindow[1]",
        "Application window",
    )
    title = IosLocator.accessibility_id("fixture-title", "Fixture title")
    camera_button = IosLocator.accessibility_id("request-camera", "Camera button")
    microphone_button = IosLocator.accessibility_id(
        "request-microphone",
        "Microphone button",
    )
    camera_status = IosLocator.accessibility_id("camera-status", "Camera status")
    microphone_status = IosLocator.accessibility_id(
        "microphone-status",
        "Microphone status",
    )
    notification_button = IosLocator.accessibility_id(
        "request-notifications",
        "Notification permission button",
    )
    send_notification_button = IosLocator.accessibility_id(
        "send-notification",
        "Send notification button",
    )
    notification_status = IosLocator.accessibility_id(
        "notification-status",
        "Notification status",
    )
    deep_link_button = IosLocator.accessibility_id(
        "simulate-deep-link",
        "Deep link button",
    )
    deep_link_status = IosLocator.accessibility_id(
        "deep-link-status",
        "Deep link status",
    )
    write_file_button = IosLocator.accessibility_id("write-file", "Write file button")
    read_file_button = IosLocator.accessibility_id("read-file", "Read file button")
    file_status = IosLocator.accessibility_id("file-status", "File status")
    background_status = IosLocator.accessibility_id(
        "background-status",
        "Background status",
    )


def _provider_is_runnable() -> bool:
    provider = os.getenv("QA_IOS_DEVICE_PROVIDER", "local").lower()
    return provider in CLOUD_PROVIDERS or sys.platform == "darwin"


def _handle_permission_prompt(driver: Any, action: IosAlertAction) -> None:
    IosSystemAlerts(driver, timeout_seconds=15.0).handle(action)


def _capture_step(diagnostics: IosDiagnostics, step: str) -> None:
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
        name=f"Screenshot: {step}",
        attachment_type=allure.attachment_type.PNG,
    )
    allure.attach.file(
        str(capture.page_source_path),
        name=f"Page source: {step}",
        attachment_type=allure.attachment_type.XML,
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("iOS System Interactions")
@allure.story("Week 19 fixture")
@pytest.mark.ios
@pytest.mark.smoke
@pytest.mark.skipif(
    not _provider_is_runnable(),
    reason="Week 19 iOS fixture requires macOS or a cloud provider.",
)
@pytest.mark.timeout(900)
@allure.testcase("SMOKE-IOS-SYSTEM-019", "iOS system interactions")
@allure.link(
    "docs/runbooks/ios-permissions-notifications-triage.md",
    name="iOS system interaction triage",
)
def test_week19_ios_fixture_system_interactions(settings: Settings) -> None:
    driver = create_ios_driver(settings)
    wait = MobileWait(driver, WaitPolicy(timeout_seconds=15.0))
    diagnostics = IosDiagnostics(
        driver,
        Path("artifacts/ios-diagnostics"),
    )

    try:
        screen = FixtureScreen(driver, wait_policy=WaitPolicy(timeout_seconds=15.0))
        screen.wait_ready()
        wait.text_is(
            screen.element(),
            FixtureScreen.title,
            "QA iOS Fixture",
        )
        _capture_step(diagnostics, "01-fixture-ready")

        screen.tap(FixtureScreen.camera_button)
        _handle_permission_prompt(driver, IosAlertAction.ACCEPT)
        wait.text_is(screen.scope(), FixtureScreen.camera_status, "camera: granted")
        _capture_step(diagnostics, "02-camera-granted")

        screen.tap(FixtureScreen.microphone_button)
        _handle_permission_prompt(driver, IosAlertAction.DISMISS)
        wait.text_is(
            screen.scope(),
            FixtureScreen.microphone_status,
            "microphone: denied",
        )
        _capture_step(diagnostics, "03-microphone-denied")

        screen.tap(FixtureScreen.notification_button)
        _handle_permission_prompt(driver, IosAlertAction.ACCEPT)
        wait.text_is(
            screen.scope(),
            FixtureScreen.notification_status,
            "notifications: authorized",
        )
        _capture_step(diagnostics, "04-notification-authorized")
        screen.tap(FixtureScreen.send_notification_button)
        wait.text_is(
            screen.scope(),
            FixtureScreen.notification_status,
            "notifications: scheduled",
        )
        _capture_step(diagnostics, "05-notification-scheduled")

        screen.tap(FixtureScreen.deep_link_button)
        wait.text_is(
            screen.scope(),
            FixtureScreen.deep_link_status,
            "deep link: opened qaweek19://system-interactions?case=deep-link",
        )
        _capture_step(diagnostics, "06-deep-link")

        screen.tap(FixtureScreen.write_file_button)
        wait.text_is(screen.scope(), FixtureScreen.file_status, "file: written")
        _capture_step(diagnostics, "07-file-written")
        screen.tap(FixtureScreen.read_file_button)
        wait.text_is(
            screen.scope(),
            FixtureScreen.file_status,
            "file: read week19-file",
        )
        _capture_step(diagnostics, "08-file-read")

        try:
            webview_context = WebDriverWait(
                driver,
                timeout=20,
                poll_frequency=0.5,
            ).until(
                lambda current: next(
                    (
                        context
                        for context in current.contexts
                        if "WEBVIEW" in context.upper()
                    ),
                    None,
                )
            )
        except TimeoutException:
            webview_context = None

        if webview_context is not None:
            driver.switch_to.context(webview_context)
            web_status = driver.find_element(AppiumBy.CSS_SELECTOR, "#web-status")
            assert web_status.text == "ready"
            driver.switch_to.context("NATIVE_APP")
            webview_mode = "context"
        else:
            page_source = driver.page_source
            assert "QA WebView" in page_source
            assert "ready" in page_source
            webview_mode = "native-page-source-fallback"

        allure.attach(
            json.dumps({"webview_mode": webview_mode}),
            name="WebView validation mode",
            attachment_type=allure.attachment_type.JSON,
        )
        _capture_step(diagnostics, "09-webview")

        driver.background_app(1)
        WebDriverWait(driver, timeout=15, poll_frequency=0.5).until(
            lambda current: current.find_element(
                *FixtureScreen.background_status.as_tuple()
            ).text.startswith("background: resumed")
        )
        _capture_step(diagnostics, "10-background-resumed")

    finally:
        _capture_step(diagnostics, "99-final")
        driver.quit()
