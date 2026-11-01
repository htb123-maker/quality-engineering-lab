"""Shared locators and bounded interactions for the QA iOS fixture."""

from __future__ import annotations

import os
import sys
from typing import Any

from qa_core.mobile.screens import Screen
from qa_core.mobile.waits import MobileWait, WaitPolicy
from qa_core.platforms.ios import (
    IosAlertAction,
    IosAlertTimeout,
    IosLocator,
    IosSystemAlerts,
)

CLOUD_PROVIDERS = {"browserstack", "saucelabs", "lambdatest"}
DEEP_LINK = "qaweek19://system-interactions?case=external-cold-start"
ALTERNATE_DEEP_LINK = "qaweek19://system-interactions?case=week21-regression"


def ios_runtime_is_configured() -> bool:
    """Return whether this host or provider can create an iOS session."""

    provider = os.getenv("QA_IOS_DEVICE_PROVIDER", "local").lower()
    return provider in CLOUD_PROVIDERS or sys.platform == "darwin"


class FixtureScreen(Screen):
    """Stable root and accessibility identifiers from the iOS fixture."""

    root_locator = IosLocator.class_chain(
        "**/XCUIElementTypeWindow[1]",
        "Application window",
    )
    title = IosLocator.accessibility_id("fixture-title", "Fixture title")
    status = IosLocator.accessibility_id("fixture-status", "Fixture status")
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
    webview_title = IosLocator.accessibility_id("webview-title", "WebView title")
    webview = IosLocator.accessibility_id("fixture-webview", "Fixture WebView")


def open_fixture(
    driver: Any,
    *,
    timeout_seconds: float = 30.0,
) -> tuple[FixtureScreen, MobileWait]:
    """Wait for the fixture root and title using explicit deadlines."""

    screen = FixtureScreen(
        driver,
        wait_policy=WaitPolicy(timeout_seconds=timeout_seconds),
    )
    wait = MobileWait(
        driver,
        WaitPolicy(timeout_seconds=timeout_seconds),
    )
    screen.wait_ready()
    wait.text_is(screen.scope(), FixtureScreen.title, "QA iOS Fixture")
    return screen, wait


def reset_permission(driver: Any, service: str) -> None:
    """Reset one permission through the XCUITest permission command."""

    driver.execute_script("mobile: resetPermission", {"service": service})


def relaunch_fixture(driver: Any, bundle_id: str) -> None:
    """Terminate and reactivate the fixture without recreating the session."""

    driver.terminate_app(bundle_id)
    driver.activate_app(bundle_id)


def handle_permission_prompt(
    driver: Any,
    action: IosAlertAction,
    *,
    timeout_seconds: float = 15.0,
) -> None:
    """Handle one expected permission alert with a bounded wait."""

    IosSystemAlerts(driver, timeout_seconds=timeout_seconds).handle(action)


def handle_optional_permission_prompt(driver: Any) -> bool:
    """Accept a permission alert only when it appears within a short deadline."""

    try:
        handle_permission_prompt(
            driver,
            IosAlertAction.ACCEPT,
            timeout_seconds=3.0,
        )
    except IosAlertTimeout:
        return False
    return True
