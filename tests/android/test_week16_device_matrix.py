"""Week 16 Android device-matrix regression suite."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from collections.abc import Iterator

import allure
import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.mobile.locators import Locator, LocatorStrategy
from qa_core.mobile.waits import MobileWait
from qa_core.platforms.android import (
    AndroidActivities,
    AndroidClipboard,
    AndroidDeviceProfile,
    AndroidFiles,
    AndroidGestures,
    AndroidIntent,
    AndroidPermissions,
    AndroidWebView,
    PermissionState,
    SwipeDirection,
)
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import WebDriverWait

from tests.android.conftest import (
    FIXTURE_ACTIVITY,
    FIXTURE_PACKAGE,
    attach_android_device_metadata,
)
from tests.android.week16_fixture import (
    CAMERA,
    COUNTER,
    COUNTER_VALUE,
    DIALOG_CANCEL,
    DIALOG_CONFIRM,
    DIALOG_TITLE,
    FORM_STATUS,
    INPUT,
    MODAL,
    RESET,
    RESUME,
    STATUS,
    SUBMIT,
    TITLE,
    FixtureScreen,
    fixture_wait_policy,
    reset_fixture_app,
)

pytestmark = [pytest.mark.android, pytest.mark.timeout(300)]
CAMERA_PERMISSION = "android.permission.CAMERA"


@pytest.fixture
def fixture_screen(
    android_fixture_device: WebDriver,
    android_settings: Settings,
) -> FixtureScreen:
    """Reset the fixture before every matrix test."""

    return reset_fixture_app(android_fixture_device, android_settings)


@pytest.fixture(autouse=True)
def attach_week16_device_metadata(
    android_worker_profile: AndroidDeviceProfile,
) -> Iterator[None]:
    """Attach the logical device matrix entry to each result."""

    attach_android_device_metadata(android_worker_profile)
    yield


def wait_for_text(
    driver: WebDriver,
    screen: FixtureScreen,
    locator: Locator,
    expected: str,
    settings: Settings,
) -> None:
    """Wait until one fixture element exposes the expected text."""

    policy = fixture_wait_policy(settings)
    WebDriverWait(
        driver,
        timeout=policy.timeout_seconds,
        poll_frequency=policy.poll_interval_seconds,
    ).until(
        lambda _: screen.text_of(locator) == expected,
        message=f"waiting for {locator} text {expected!r}",
    )


def hide_keyboard(driver: WebDriver) -> None:
    """Hide the software keyboard when the input action opened it."""

    try:
        driver.hide_keyboard()
    except WebDriverException:
        pass


# Device and application baseline: 12 tests.


@allure.story("Device baseline")
def test_android_session_id_is_present(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.driver.session_id


@allure.story("Device baseline")
def test_fixture_package_is_in_the_foreground(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.driver.current_package == FIXTURE_PACKAGE


@allure.story("Device baseline")
def test_fixture_activity_is_in_the_foreground(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.driver.current_activity == FIXTURE_ACTIVITY


@allure.story("Device baseline")
def test_window_width_is_positive(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.driver.get_window_size()["width"] > 0


@allure.story("Device baseline")
def test_window_height_is_positive(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.driver.get_window_size()["height"] > 0


@allure.story("Device baseline")
def test_title_is_a_visible_screen_root(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.element().is_displayed()


@allure.story("Device baseline")
def test_title_text_is_stable(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.text_of(TITLE) == "QA Android Fixture"


@allure.story("Device baseline")
def test_fixture_status_starts_ready(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.text_of(STATUS) == "Ready"


@allure.story("Device baseline")
def test_resume_counter_is_visible(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.text_of(RESUME).startswith("Resume count:")


@allure.story("Device baseline")
def test_camera_action_is_present(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.descendant(CAMERA).is_displayed()


@allure.story("Device baseline")
def test_form_input_exposes_hint(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.text_of(INPUT) == "Test input"


@allure.story("Device baseline")
def test_fixture_starts_in_portrait(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.driver.orientation.lower() == "portrait"


# Form behavior: 12 tests.


@allure.story("Form validation")
def test_empty_submit_requires_input(fixture_screen: FixtureScreen) -> None:
    fixture_screen.tap(SUBMIT)
    assert fixture_screen.text_of(FORM_STATUS) == "Input required"


@allure.story("Form validation")
def test_input_is_enabled(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.descendant(INPUT).is_enabled()


@allure.story("Form validation")
def test_submit_is_enabled(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.descendant(SUBMIT).is_enabled()


@allure.story("Form validation")
def test_reset_is_enabled(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.descendant(RESET).is_enabled()


@allure.story("Form input")
@pytest.mark.parametrize(
    "value",
    [
        "A",
        "360",
        "qa-user",
        "camera grant",
        "  padded  ",
        "user_01",
        "line-1",
        "x" * 64,
    ],
    ids=[
        "single-character",
        "numeric",
        "username",
        "sentence",
        "padded",
        "underscore",
        "hyphen",
        "long-value",
    ],
)
def test_form_round_trip_preserves_value(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
    value: str,
) -> None:
    fixture_screen.send_keys(INPUT, value)
    hide_keyboard(fixture_screen.driver)
    fixture_screen.tap(SUBMIT)
    wait_for_text(
        fixture_screen.driver,
        fixture_screen,
        FORM_STATUS,
        f"Submitted: {value}",
        android_settings,
    )


# Counter state: 4 tests.


@allure.story("Counter")
def test_counter_starts_at_zero(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.text_of(COUNTER_VALUE) == "Counter: 0"


@allure.story("Counter")
def test_counter_increments_once(fixture_screen: FixtureScreen) -> None:
    fixture_screen.tap(COUNTER)
    assert fixture_screen.text_of(COUNTER_VALUE) == "Counter: 1"


@allure.story("Counter")
def test_counter_increments_five_times(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    for _ in range(5):
        fixture_screen.tap(COUNTER)
    wait_for_text(
        fixture_screen.driver,
        fixture_screen,
        COUNTER_VALUE,
        "Counter: 5",
        android_settings,
    )


@allure.story("Counter")
def test_reset_restores_counter_to_zero(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    fixture_screen.tap(COUNTER)
    fixture_screen.tap(RESET)
    wait_for_text(
        fixture_screen.driver,
        fixture_screen,
        COUNTER_VALUE,
        "Counter: 0",
        android_settings,
    )


# Dialog behavior: 4 tests.


@allure.story("Dialog")
def test_dialog_action_is_available(fixture_screen: FixtureScreen) -> None:
    assert fixture_screen.descendant(MODAL).is_displayed()


@allure.story("Dialog")
def test_dialog_opens_with_expected_title(fixture_screen: FixtureScreen) -> None:
    fixture_screen.tap(MODAL)
    assert fixture_screen.descendant(DIALOG_TITLE).is_displayed()


@allure.story("Dialog")
def test_dialog_cancel_updates_form_status(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    fixture_screen.tap(MODAL)
    MobileWait(
        fixture_screen.driver,
        fixture_wait_policy(android_settings),
    ).clickable(fixture_screen.driver, DIALOG_CANCEL).click()
    wait_for_text(
        fixture_screen.driver,
        fixture_screen,
        FORM_STATUS,
        "Dialog canceled",
        android_settings,
    )


@allure.story("Dialog")
def test_dialog_confirm_updates_form_status(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    fixture_screen.tap(MODAL)
    MobileWait(
        fixture_screen.driver,
        fixture_wait_policy(android_settings),
    ).clickable(fixture_screen.driver, DIALOG_CONFIRM).click()
    wait_for_text(
        fixture_screen.driver,
        fixture_screen,
        FORM_STATUS,
        "Dialog confirmed",
        android_settings,
    )


# Gesture behavior: 4 tests.


@allure.story("Gesture")
@pytest.mark.parametrize(
    "direction",
    [SwipeDirection.UP, SwipeDirection.DOWN, SwipeDirection.LEFT, SwipeDirection.RIGHT],
    ids=["up", "down", "left", "right"],
)
def test_window_accepts_directional_swipe(
    fixture_screen: FixtureScreen,
    direction: SwipeDirection,
) -> None:
    AndroidGestures(fixture_screen.driver).swipe(
        direction,
        percent=0.2,
        speed=1_500,
    )
    assert fixture_screen.driver.current_package == FIXTURE_PACKAGE
    assert fixture_screen.descendant(TITLE).is_displayed()


# Permission state: 4 tests.


@allure.story("Permissions")
def test_camera_permission_is_declared(fixture_screen: FixtureScreen) -> None:
    snapshot = AndroidPermissions(fixture_screen.driver, FIXTURE_PACKAGE).snapshot()
    assert CAMERA_PERMISSION in snapshot.requested


@allure.story("Permissions")
def test_camera_permission_can_be_granted(fixture_screen: FixtureScreen) -> None:
    permissions = AndroidPermissions(fixture_screen.driver, FIXTURE_PACKAGE)
    original = permissions.snapshot()
    try:
        assert (
            permissions.grant(CAMERA_PERMISSION).state_of(CAMERA_PERMISSION)
            is PermissionState.GRANTED
        )
    finally:
        if CAMERA_PERMISSION in original.granted:
            permissions.grant(CAMERA_PERMISSION)
        else:
            permissions.revoke(CAMERA_PERMISSION)


@allure.story("Permissions")
def test_camera_permission_can_be_revoked(fixture_screen: FixtureScreen) -> None:
    permissions = AndroidPermissions(fixture_screen.driver, FIXTURE_PACKAGE)
    original = permissions.snapshot()
    try:
        assert (
            permissions.revoke(CAMERA_PERMISSION).state_of(CAMERA_PERMISSION)
            is PermissionState.DENIED
        )
    finally:
        if CAMERA_PERMISSION in original.granted:
            permissions.grant(CAMERA_PERMISSION)
        else:
            permissions.revoke(CAMERA_PERMISSION)


@allure.story("Permissions")
def test_repeated_camera_grant_is_idempotent(fixture_screen: FixtureScreen) -> None:
    permissions = AndroidPermissions(fixture_screen.driver, FIXTURE_PACKAGE)
    original = permissions.snapshot()
    try:
        permissions.grant(CAMERA_PERMISSION)
        assert (
            permissions.grant(CAMERA_PERMISSION).state_of(CAMERA_PERMISSION)
            is PermissionState.GRANTED
        )
    finally:
        if CAMERA_PERMISSION in original.granted:
            permissions.grant(CAMERA_PERMISSION)
        else:
            permissions.revoke(CAMERA_PERMISSION)


# Hybrid context: 4 tests.


@allure.story("Hybrid")
def test_fixture_webview_context_is_available(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    hybrid = AndroidWebView(fixture_screen.driver, fixture_wait_policy(android_settings))
    assert hybrid.context_for_package(FIXTURE_PACKAGE) == f"WEBVIEW_{FIXTURE_PACKAGE}"


@allure.story("Hybrid")
def test_webview_heading_is_visible(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    hybrid = AndroidWebView(fixture_screen.driver, fixture_wait_policy(android_settings))
    with hybrid.activate(FIXTURE_PACKAGE):
        assert fixture_screen.driver.find_element(
            "css selector",
            "#fixture-hybrid",
        ).text == "Hybrid ready"


@allure.story("Hybrid")
def test_webview_button_accepts_a_click(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    hybrid = AndroidWebView(fixture_screen.driver, fixture_wait_policy(android_settings))
    with hybrid.activate(FIXTURE_PACKAGE):
        button = fixture_screen.driver.find_element(
            "css selector",
            "#fixture-web-button",
        )
        button.click()
        assert button.is_displayed()


@allure.story("Hybrid")
def test_native_context_is_restored_after_webview(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    hybrid = AndroidWebView(fixture_screen.driver, fixture_wait_policy(android_settings))
    with hybrid.activate(FIXTURE_PACKAGE):
        pass
    assert fixture_screen.driver.current_context == "NATIVE_APP"
    assert fixture_screen.driver.current_package == FIXTURE_PACKAGE


# Device file and clipboard state: 4 tests.


@allure.story("Device files")
def test_device_file_round_trip(fixture_screen: FixtureScreen) -> None:
    files = AndroidFiles(fixture_screen.driver)
    path = AndroidFiles.temporary_path()
    try:
        files.write_text(path, "week16-device-file")
        assert files.read_text(path) == "week16-device-file"
    finally:
        files.delete(path)


@allure.story("Device files")
def test_empty_device_file_can_be_read(fixture_screen: FixtureScreen) -> None:
    files = AndroidFiles(fixture_screen.driver)
    path = AndroidFiles.temporary_path()
    try:
        files.write_text(path, "")
        assert files.read_text(path) == ""
    finally:
        files.delete(path)


@allure.story("Device files")
def test_device_file_is_deleted(fixture_screen: FixtureScreen) -> None:
    files = AndroidFiles(fixture_screen.driver)
    path = AndroidFiles.temporary_path()
    files.write_text(path, "delete-me")
    files.delete(path)
    assert not files.exists(path)


@allure.story("Clipboard")
def test_clipboard_value_is_restored(fixture_screen: FixtureScreen) -> None:
    clipboard = AndroidClipboard(fixture_screen.driver)
    original = clipboard.get_text()
    with clipboard.preserve():
        clipboard.set_text("week16-clipboard")
        assert clipboard.get_text() == "week16-clipboard"
    assert clipboard.get_text() == original


# Deep links and foreground recovery: 6 tests.


@allure.story("Deep link")
@pytest.mark.parametrize(
    "deep_link",
    [
        "qaweek15://permission/week16-alpha",
        "qaweek15://permission/week16-beta",
        "qaweek15://permission/week16-gamma",
    ],
    ids=["alpha", "beta", "gamma"],
)
def test_deep_link_reaches_fixture_screen(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
    deep_link: str,
) -> None:
    component = f"{FIXTURE_PACKAGE}/{FIXTURE_ACTIVITY}"
    AndroidActivities(
        fixture_screen.driver,
        fixture_wait_policy(android_settings),
    ).start(
        AndroidIntent(
            action="android.intent.action.VIEW",
            uri=deep_link,
            component=component,
            stop=True,
        )
    )
    status = MobileWait(
        fixture_screen.driver,
        fixture_wait_policy(android_settings),
    ).visible(
        fixture_screen.driver,
        Locator(
            LocatorStrategy.ACCESSIBILITY_ID,
            f"fixture-status:deep-link:{deep_link}",
            "Deep link status",
        ),
    )
    assert deep_link in status.text


@allure.story("Recovery")
def test_home_leaves_fixture_package(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    activities = AndroidActivities(
        fixture_screen.driver,
        fixture_wait_policy(android_settings),
    )
    activities.go_home()
    activities.wait_for_package(android_settings.android_app_package)
    assert fixture_screen.driver.current_package == android_settings.android_app_package


@allure.story("Recovery")
def test_restart_returns_to_fixture_activity(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    activities = AndroidActivities(
        fixture_screen.driver,
        fixture_wait_policy(android_settings),
    )
    component = f"{FIXTURE_PACKAGE}/{FIXTURE_ACTIVITY}"
    activities.go_home()
    activities.start(
        AndroidIntent(
            action="android.intent.action.MAIN",
            component=component,
        )
    )
    assert fixture_screen.driver.current_package == FIXTURE_PACKAGE
    assert fixture_screen.driver.current_activity == FIXTURE_ACTIVITY


@allure.story("Recovery")
def test_resume_evidence_is_visible_after_restart(
    fixture_screen: FixtureScreen,
    android_settings: Settings,
) -> None:
    activities = AndroidActivities(
        fixture_screen.driver,
        fixture_wait_policy(android_settings),
    )
    component = f"{FIXTURE_PACKAGE}/{FIXTURE_ACTIVITY}"
    activities.go_home()
    activities.start(
        AndroidIntent(
            action="android.intent.action.MAIN",
            component=component,
        )
    )
    assert fixture_screen.descendant(RESUME).is_displayed()
