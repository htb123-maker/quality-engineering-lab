"""Android permission, Hybrid, file, deep-link, and recovery smoke tests."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import allure
import pytest
from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.mobile.locators import Locator, LocatorStrategy
from qa_core.mobile.waits import MobileWait, WaitPolicy
from qa_core.platforms.android import (
    AndroidActivities,
    AndroidClipboard,
    AndroidFiles,
    AndroidIntent,
    AndroidPermissions,
    AndroidWebView,
    PermissionState,
)

from tests.android.conftest import FIXTURE_ACTIVITY, FIXTURE_PACKAGE

CAMERA_PERMISSION = "android.permission.CAMERA"
PERMISSION_CONTROLLER = "com.android.permissioncontroller"
ALLOW_CAMERA_ID = (
    "com.android.permissioncontroller:id/permission_allow_foreground_only_button"
)


def fixture_wait(settings: Settings) -> WaitPolicy:
    """Use the same bounded UI wait policy as other Android tests."""

    return WaitPolicy(
        timeout_seconds=settings.android_ui_wait_timeout_seconds,
        poll_interval_seconds=settings.android_ui_wait_poll_seconds,
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("Android system interactions")
@allure.story("Permission dialog")
@pytest.mark.android
@pytest.mark.smoke
@pytest.mark.timeout(300)
@allure.testcase("SMOKE-ANDROID-PERMISSION-001", "Android permission dialog")
@allure.link(
    "docs/runbooks/android-permissions-and-recovery-triage.md",
    name="System interaction triage",
)
def test_permission_dialog_grants_and_reports_camera_access(
    settings: Settings,
    android_fixture_driver: WebDriver,
) -> None:
    driver = android_fixture_driver
    policy = fixture_wait(settings)
    permissions = AndroidPermissions(driver, FIXTURE_PACKAGE)
    activities = AndroidActivities(driver, policy)
    waits = MobileWait(driver, policy)
    original = permissions.snapshot()

    try:
        permissions.revoke(CAMERA_PERMISSION)
        driver.find_element(AppiumBy.ACCESSIBILITY_ID, "request-camera").click()

        assert activities.wait_for_package(PERMISSION_CONTROLLER) == PERMISSION_CONTROLLER
        dialog = waits.visible(
            driver,
            Locator(
                LocatorStrategy.RESOURCE_ID,
                ALLOW_CAMERA_ID,
                "Allow camera while using the app",
            ),
        )
        dialog.click()

        activities.wait_for_component(f"{FIXTURE_PACKAGE}/{FIXTURE_ACTIVITY}")
        granted_status = waits.visible(
            driver,
            Locator(
                LocatorStrategy.ACCESSIBILITY_ID,
                "fixture-status:camera-granted",
                "Camera granted status",
            ),
        )
        assert granted_status.text == "Camera granted"
        assert permissions.snapshot().state_of(CAMERA_PERMISSION) is PermissionState.GRANTED
    finally:
        if CAMERA_PERMISSION in original.granted:
            permissions.grant(CAMERA_PERMISSION)
        else:
            permissions.revoke(CAMERA_PERMISSION)


@allure.epic("Quality Engineering Lab")
@allure.feature("Android system interactions")
@allure.story("Hybrid context")
@pytest.mark.android
@pytest.mark.smoke
@pytest.mark.timeout(300)
@allure.testcase("SMOKE-ANDROID-HYBRID-001", "Android native and WebView contexts")
def test_hybrid_context_switches_to_webview_and_restores_native(
    settings: Settings,
    android_fixture_driver: WebDriver,
) -> None:
    driver = android_fixture_driver
    hybrid = AndroidWebView(driver, fixture_wait(settings))

    with hybrid.activate(FIXTURE_PACKAGE) as context:
        assert context == f"WEBVIEW_{FIXTURE_PACKAGE}"
        assert driver.find_element("css selector", "#fixture-hybrid").text == "Hybrid ready"
        driver.find_element("css selector", "#fixture-web-button").click()
        assert driver.find_element("css selector", "#fixture-web-button").is_displayed()

    assert driver.current_context == "NATIVE_APP"
    assert driver.current_package == FIXTURE_PACKAGE


@allure.epic("Quality Engineering Lab")
@allure.feature("Android system interactions")
@allure.story("Device files and clipboard")
@pytest.mark.android
@pytest.mark.smoke
@pytest.mark.timeout(300)
@allure.testcase("SMOKE-ANDROID-FILE-001", "Android file and clipboard round trip")
def test_device_file_and_clipboard_round_trip(
    android_fixture_driver: WebDriver,
) -> None:
    driver = android_fixture_driver
    files = AndroidFiles(driver)
    clipboard = AndroidClipboard(driver)
    remote_path = AndroidFiles.temporary_path()
    payload = "week15-device-file-evidence"

    try:
        files.write_text(remote_path, payload)
        assert files.read_text(remote_path) == payload

        with clipboard.preserve():
            clipboard.set_text("week15-clipboard-evidence")
            assert clipboard.get_text() == "week15-clipboard-evidence"
    finally:
        files.delete(remote_path)

    assert not files.exists(remote_path)


@allure.epic("Quality Engineering Lab")
@allure.feature("Android system interactions")
@allure.story("Deep link and recovery")
@pytest.mark.android
@pytest.mark.smoke
@pytest.mark.timeout(300)
@allure.testcase("SMOKE-ANDROID-RECOVERY-001", "Android deep link and foreground recovery")
def test_deep_link_and_background_recovery(
    settings: Settings,
    android_fixture_driver: WebDriver,
) -> None:
    driver = android_fixture_driver
    policy = fixture_wait(settings)
    activities = AndroidActivities(driver, policy)
    waits = MobileWait(driver, policy)
    component = f"{FIXTURE_PACKAGE}/{FIXTURE_ACTIVITY}"
    deep_link = "qaweek15://permission/week15"
    intent = AndroidIntent(
        action="android.intent.action.VIEW",
        uri=deep_link,
        component=component,
        stop=True,
    )

    activities.start(intent)
    deep_link_status = waits.visible(
        driver,
        Locator(
            LocatorStrategy.ACCESSIBILITY_ID,
            f"fixture-status:deep-link:{deep_link}",
            "Deep link status",
        ),
    )
    assert deep_link in deep_link_status.text

    activities.go_home()
    activities.wait_for_package_not(FIXTURE_PACKAGE)

    activities.start(
        AndroidIntent(
            action="android.intent.action.VIEW",
            uri=deep_link,
            component=component,
        )
    )
    assert driver.current_package == FIXTURE_PACKAGE
    assert driver.current_activity == FIXTURE_ACTIVITY
    assert waits.visible(
        driver,
        Locator(
            LocatorStrategy.ACCESSIBILITY_ID,
            "fixture-resume",
            "Fixture resume counter",
        ),
    ).is_displayed()
