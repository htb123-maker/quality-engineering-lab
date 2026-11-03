"""Week 21 fixture structure and accessibility acceptance."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from typing import Any

import allure
import pytest

from tests.ios.fixture import FixtureScreen, open_fixture

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

pytestmark = [
    pytest.mark.ios,
    pytest.mark.timeout(900),
]


@allure.feature("iOS Week 21")
@allure.story("Fixture UI inventory")
@allure.testcase("IOS-UI-001")
def test_fixture_title_is_visible(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    title = screen.wait.visible(screen.element(), FixtureScreen.title)
    assert title.text == "QA iOS Fixture"
    assert title.is_displayed()


@allure.testcase("IOS-UI-002")
def test_fixture_status_is_ready(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    assert screen.text_of(FixtureScreen.status) == "ready"


@allure.testcase("IOS-UI-003")
def test_camera_status_is_rendered(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    assert screen.text_of(FixtureScreen.camera_status).startswith("camera: ")


@allure.testcase("IOS-UI-004")
def test_microphone_status_is_rendered(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    assert screen.text_of(FixtureScreen.microphone_status).startswith(
        "microphone: "
    )


@allure.testcase("IOS-UI-005")
def test_notification_status_is_rendered(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    assert screen.text_of(FixtureScreen.notification_status).startswith(
        "notifications: "
    )


@allure.testcase("IOS-UI-006")
def test_deep_link_status_is_rendered(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    assert screen.text_of(FixtureScreen.deep_link_status).startswith("deep link: ")


@allure.testcase("IOS-UI-007")
def test_file_status_starts_idle(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    _ = screen.text_of(FixtureScreen.file_status)
    assert screen.wait.text_is(
        screen.element(),
        FixtureScreen.file_status,
        "file: idle",
    ).is_displayed()


@allure.testcase("IOS-UI-008")
def test_background_status_starts_with_launch_count(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    assert screen.text_of(FixtureScreen.background_status).startswith(
        "background: launches="
    )


@allure.testcase("IOS-UI-009")
def test_webview_title_is_visible(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    assert screen.wait.visible(
        screen.element(),
        FixtureScreen.webview_title,
    ).is_displayed()


@allure.testcase("IOS-UI-010")
def test_webview_native_container_is_visible(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    assert screen.wait.visible(screen.element(), FixtureScreen.webview).is_displayed()


@allure.testcase("IOS-UI-011")
def test_primary_control_buttons_are_visible(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)
    controls = (
        FixtureScreen.camera_button,
        FixtureScreen.microphone_button,
        FixtureScreen.notification_button,
        FixtureScreen.send_notification_button,
        FixtureScreen.deep_link_button,
        FixtureScreen.write_file_button,
        FixtureScreen.read_file_button,
    )

    for control in controls:
        assert screen.wait.visible(screen.element(), control).is_displayed()


@allure.testcase("IOS-UI-012")
def test_page_source_contains_stable_identifiers(ios_runtime_driver: Any) -> None:
    open_fixture(ios_runtime_driver)
    source = ios_runtime_driver.page_source

    for identifier in (
        "fixture-title",
        "fixture-status",
        "request-camera",
        "write-file",
        "fixture-webview",
    ):
        assert identifier in source


@allure.testcase("IOS-UI-013")
def test_window_dimensions_are_positive(ios_runtime_driver: Any) -> None:
    open_fixture(ios_runtime_driver)
    size = ios_runtime_driver.get_window_size()

    assert size["width"] > 0
    assert size["height"] > 0


@allure.testcase("IOS-UI-014")
def test_screenshot_contains_png_bytes(ios_runtime_driver: Any) -> None:
    open_fixture(ios_runtime_driver)
    screenshot = ios_runtime_driver.get_screenshot_as_png()

    assert screenshot.startswith(PNG_SIGNATURE)
    assert len(screenshot) > len(PNG_SIGNATURE)
