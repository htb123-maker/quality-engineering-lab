"""Unit tests for Android permission, intent, file, clipboard, and Hybrid helpers."""

from __future__ import annotations

from typing import cast

import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.android import (
    AndroidActivities,
    AndroidActivityTimeout,
    AndroidClipboard,
    AndroidFiles,
    AndroidIntent,
    AndroidPermissions,
    AndroidWebView,
    PermissionState,
    WebViewContextTimeout,
)

CAMERA = "android.permission.CAMERA"


def fast_policy() -> WaitPolicy:
    """Keep timeout tests bounded and fast."""

    return WaitPolicy(timeout_seconds=0.05, poll_interval_seconds=0.005)


class FakePermissionDriver:
    """In-memory stand-in for UiAutomator2 permission commands."""

    def __init__(self) -> None:
        self.requested = {CAMERA}
        self.granted: set[str] = set()
        self.changes: list[tuple[list[str], str]] = []

    def execute_script(self, script: str, argument: object) -> object:
        assert isinstance(argument, dict)
        if script == "mobile: getPermissions":
            permission_type = argument["type"]
            if permission_type == "requested":
                return list(self.requested | self.requested)
            if permission_type == "granted":
                return list(self.granted)
            return list(self.requested - self.granted)
        if script == "mobile: changePermissions":
            permissions = argument["permissions"]
            action = argument["action"]
            assert isinstance(permissions, list)
            assert isinstance(action, str)
            self.changes.append((permissions, action))
            if action == "grant":
                self.granted.update(permissions)
            else:
                self.granted.difference_update(permissions)
            return None
        raise AssertionError(f"unexpected script: {script}")


@pytest.mark.unit
def test_permission_snapshot_normalizes_duplicate_commands() -> None:
    permissions = AndroidPermissions(
        cast(WebDriver, FakePermissionDriver()),
        "com.example.app",
    )

    snapshot = permissions.snapshot()

    assert snapshot.requested == frozenset({CAMERA})
    assert snapshot.state_of(CAMERA) is PermissionState.DENIED


@pytest.mark.unit
def test_permission_grant_revoke_and_unrequested_validation() -> None:
    driver = FakePermissionDriver()
    permissions = AndroidPermissions(cast(WebDriver, driver), "com.example.app")

    granted = permissions.grant(CAMERA)
    assert granted.state_of(CAMERA) is PermissionState.GRANTED
    revoked = permissions.revoke(CAMERA)
    assert revoked.state_of(CAMERA) is PermissionState.DENIED
    assert driver.changes == [([CAMERA], "grant"), ([CAMERA], "revoke")]

    with pytest.raises(ValueError, match="does not request"):
        permissions.grant("android.permission.READ_SMS")


class FakeActivityDriver:
    """Track explicit intent launches and key events."""

    def __init__(self, package: str, activity: str) -> None:
        self.current_package = package
        self.current_activity = activity
        self.intents: list[dict[str, object]] = []
        self.keycodes: list[int] = []

    def execute_script(self, script: str, argument: dict[str, object]) -> None:
        assert script == "mobile: startActivity"
        self.intents.append(argument)
        component = argument.get("component")
        if isinstance(component, str):
            self.current_package, activity = component.split("/", 1)
            self.current_activity = activity

    def press_keycode(self, keycode: int) -> None:
        self.keycodes.append(keycode)
        self.current_package = "com.android.launcher"
        self.current_activity = ".Home"


@pytest.mark.unit
def test_intent_payload_and_component_wait() -> None:
    driver = FakeActivityDriver("com.old", ".Old")
    activities = AndroidActivities(cast(WebDriver, driver), fast_policy())
    intent = AndroidIntent(
        action="android.intent.action.VIEW",
        component="com.example.app/.MainActivity",
        uri="qaweek15://permission/test",
        categories=("android.intent.category.DEFAULT",),
    )

    activities.start(intent)

    assert driver.current_activity == ".MainActivity"
    assert driver.intents[0]["uri"] == "qaweek15://permission/test"
    activities.go_home()
    assert driver.keycodes == [3]


@pytest.mark.unit
def test_activity_wait_timeout_reports_foreground_target() -> None:
    driver = FakeActivityDriver("com.old", ".Old")
    activities = AndroidActivities(cast(WebDriver, driver), fast_policy())

    with pytest.raises(AndroidActivityTimeout, match="com.example.app"):
        activities.wait_for_component("com.example.app/.MainActivity")


class FakeFileDriver:
    """In-memory device file system."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def push_file(self, path: str, base64_data: str) -> None:
        self.files[path] = base64_data

    def pull_file(self, path: str) -> str:
        from selenium.common.exceptions import WebDriverException

        if path not in self.files:
            raise WebDriverException("missing")
        return self.files[path]

    def execute_script(self, script: str, argument: dict[str, str]) -> None:
        assert script == "mobile: deleteFile"
        self.files.pop(argument["remotePath"], None)


@pytest.mark.unit
def test_file_round_trip_and_path_validation() -> None:
    driver = FakeFileDriver()
    files = AndroidFiles(cast(WebDriver, driver))
    path = "/sdcard/Download/test.txt"

    files.write_text(path, "device evidence")
    assert files.read_text(path) == "device evidence"
    assert files.exists(path)
    files.delete(path)
    assert not files.exists(path)

    with pytest.raises(ValueError, match="absolute"):
        files.write_text("relative.txt", "invalid")
    with pytest.raises(ValueError, match="must not contain"):
        files.write_text("/sdcard/../secret", "invalid")


class FakeClipboardDriver:
    """In-memory clipboard."""

    def __init__(self) -> None:
        self.text = "before"

    def get_clipboard_text(self) -> str:
        return self.text

    def set_clipboard_text(self, value: str) -> None:
        self.text = value


@pytest.mark.unit
def test_clipboard_context_restores_previous_value() -> None:
    driver = FakeClipboardDriver()
    clipboard = AndroidClipboard(cast(WebDriver, driver))

    with clipboard.preserve():
        clipboard.set_text("inside")
        assert driver.text == "inside"

    assert driver.text == "before"


class FakeSwitchTo:
    """Switch a fake driver context."""

    def __init__(self, driver: FakeHybridDriver) -> None:
        self.driver = driver

    def context(self, name: str) -> None:
        if name not in self.driver.contexts:
            raise AssertionError(f"missing context {name}")
        self.driver.current_context = name


class FakeHybridDriver:
    """Fake native/WebView context list."""

    def __init__(self) -> None:
        self.contexts = ["NATIVE_APP", "WEBVIEW_com.example.app"]
        self.current_context = "NATIVE_APP"
        self.switch_to = FakeSwitchTo(self)


@pytest.mark.unit
def test_webview_context_is_selected_and_native_context_restored() -> None:
    driver = FakeHybridDriver()
    hybrid = AndroidWebView(cast(WebDriver, driver), fast_policy())

    with hybrid.activate("com.example.app") as context:
        assert context == "WEBVIEW_com.example.app"
        assert driver.current_context == context

    assert driver.current_context == "NATIVE_APP"


@pytest.mark.unit
def test_webview_timeout_lists_available_contexts() -> None:
    driver = FakeHybridDriver()
    driver.contexts = ["NATIVE_APP"]
    hybrid = AndroidWebView(cast(WebDriver, driver), fast_policy())

    with pytest.raises(WebViewContextTimeout, match="NATIVE_APP"):
        hybrid.context_for_package("com.example.app")
