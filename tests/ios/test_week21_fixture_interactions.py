"""Week 21 persisted fixture state and system-interaction acceptance."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from typing import Any

import allure
import pytest
from qa_core.config.settings import Settings
from selenium.webdriver.support.ui import WebDriverWait

from tests.ios.fixture import (
    ALTERNATE_DEEP_LINK,
    FixtureScreen,
    open_fixture,
    relaunch_fixture,
    reset_permission,
)

pytestmark = [
    pytest.mark.ios,
    pytest.mark.timeout(900),
]


@allure.testcase("IOS-ACT-001")
def test_in_app_deep_link_updates_status(ios_runtime_driver: Any) -> None:
    screen, wait = open_fixture(ios_runtime_driver)

    screen.tap(FixtureScreen.deep_link_button)
    wait.text_is(
        screen.scope(),
        FixtureScreen.deep_link_status,
        "deep link: opened qaweek19://system-interactions?case=deep-link",
    )


@allure.testcase("IOS-ACT-002")
def test_write_fixture_file_updates_status(ios_runtime_driver: Any) -> None:
    screen, wait = open_fixture(ios_runtime_driver)

    screen.tap(FixtureScreen.write_file_button)
    wait.text_is(screen.scope(), FixtureScreen.file_status, "file: written")


@allure.testcase("IOS-ACT-003")
def test_read_file_after_write_returns_fixture_content(ios_runtime_driver: Any) -> None:
    screen, wait = open_fixture(ios_runtime_driver)

    screen.tap(FixtureScreen.write_file_button)
    wait.text_is(screen.scope(), FixtureScreen.file_status, "file: written")
    screen.tap(FixtureScreen.read_file_button)
    wait.text_is(
        screen.scope(),
        FixtureScreen.file_status,
        "file: read week19-file",
    )


@allure.testcase("IOS-ACT-004")
def test_file_content_survives_relaunch(
    ios_runtime_driver: Any,
    settings: Settings,
) -> None:
    screen, wait = open_fixture(ios_runtime_driver)
    screen.tap(FixtureScreen.write_file_button)
    wait.text_is(screen.scope(), FixtureScreen.file_status, "file: written")

    relaunch_fixture(ios_runtime_driver, settings.ios_bundle_id)
    screen, wait = open_fixture(ios_runtime_driver)
    screen.tap(FixtureScreen.read_file_button)
    wait.text_is(
        screen.scope(),
        FixtureScreen.file_status,
        "file: read week19-file",
    )


@allure.testcase("IOS-ACT-005")
def test_deep_link_state_survives_relaunch(
    ios_runtime_driver: Any,
    settings: Settings,
) -> None:
    screen, wait = open_fixture(ios_runtime_driver)
    screen.tap(FixtureScreen.deep_link_button)
    wait.text_is(
        screen.scope(),
        FixtureScreen.deep_link_status,
        "deep link: opened qaweek19://system-interactions?case=deep-link",
    )

    relaunch_fixture(ios_runtime_driver, settings.ios_bundle_id)
    screen, wait = open_fixture(ios_runtime_driver)
    assert screen.text_of(FixtureScreen.deep_link_status) == (
        "deep link: opened qaweek19://system-interactions?case=deep-link"
    )


@allure.testcase("IOS-ACT-006")
def test_external_deep_link_accepts_week21_case(
    ios_runtime_driver: Any,
    settings: Settings,
) -> None:
    open_fixture(ios_runtime_driver)
    ios_runtime_driver.terminate_app(settings.ios_bundle_id)
    ios_runtime_driver.execute_script(
        "mobile: deepLink",
        {
            "url": ALTERNATE_DEEP_LINK,
            "bundleId": settings.ios_bundle_id,
        },
    )

    screen, wait = open_fixture(ios_runtime_driver)
    wait.text_is(
        screen.scope(),
        FixtureScreen.deep_link_status,
        f"deep link: opened {ALTERNATE_DEEP_LINK}",
    )


@allure.testcase("IOS-ACT-007")
def test_background_and_foreground_updates_resume_state(
    ios_runtime_driver: Any,
) -> None:
    open_fixture(ios_runtime_driver)

    ios_runtime_driver.background_app(1)
    WebDriverWait(ios_runtime_driver, timeout=20, poll_frequency=0.5).until(
        lambda driver: driver.find_element(
            *FixtureScreen.background_status.as_tuple()
        ).text.startswith("background: resumed")
    )


@allure.testcase("IOS-ACT-008")
def test_terminate_and_activate_recovers_fixture(
    ios_runtime_driver: Any,
    settings: Settings,
) -> None:
    open_fixture(ios_runtime_driver)
    relaunch_fixture(ios_runtime_driver, settings.ios_bundle_id)

    screen, _ = open_fixture(ios_runtime_driver)
    assert screen.element().is_displayed()


@allure.testcase("IOS-ACT-009")
def test_camera_permission_reset_restores_not_determined(
    ios_runtime_driver: Any,
    settings: Settings,
) -> None:
    reset_permission(ios_runtime_driver, "camera")
    relaunch_fixture(ios_runtime_driver, settings.ios_bundle_id)

    screen, wait = open_fixture(ios_runtime_driver)
    wait.text_is(
        screen.scope(),
        FixtureScreen.camera_status,
        "camera: not-determined",
    )


@allure.testcase("IOS-ACT-010")
def test_microphone_permission_reset_restores_not_determined(
    ios_runtime_driver: Any,
    settings: Settings,
) -> None:
    reset_permission(ios_runtime_driver, "microphone")
    relaunch_fixture(ios_runtime_driver, settings.ios_bundle_id)

    screen, wait = open_fixture(ios_runtime_driver)
    wait.text_is(
        screen.scope(),
        FixtureScreen.microphone_status,
        "microphone: not-determined",
    )


@allure.testcase("IOS-ACT-011")
def test_notification_permission_controls_are_clickable(
    ios_runtime_driver: Any,
) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    for control in (
        FixtureScreen.notification_button,
        FixtureScreen.send_notification_button,
    ):
        assert screen.wait.clickable(screen.element(), control).is_enabled()


@allure.testcase("IOS-ACT-012")
def test_repeated_file_write_remains_idempotent(ios_runtime_driver: Any) -> None:
    screen, wait = open_fixture(ios_runtime_driver)

    screen.tap(FixtureScreen.write_file_button)
    wait.text_is(screen.scope(), FixtureScreen.file_status, "file: written")
    screen.tap(FixtureScreen.write_file_button)
    wait.text_is(screen.scope(), FixtureScreen.file_status, "file: written")
    screen.tap(FixtureScreen.read_file_button)
    wait.text_is(
        screen.scope(),
        FixtureScreen.file_status,
        "file: read week19-file",
    )
