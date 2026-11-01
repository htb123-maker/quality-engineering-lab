"""Week 21 locator, wait, gesture, and hierarchy diagnostics acceptance."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import allure
import pytest
from qa_core.mobile.waits import ElementWaitTimeout, MobileWait, WaitPolicy
from qa_core.platforms.ios import IosGestures, IosLocator, IosSwipeDirection

from tests.ios.fixture import FixtureScreen, open_fixture

pytestmark = [
    pytest.mark.ios,
    pytest.mark.timeout(900),
]


@allure.testcase("IOS-FWK-001")
def test_predicate_locator_finds_fixture_title(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)
    predicate = IosLocator.predicate(
        "name == 'fixture-title' OR label == 'QA iOS Fixture'",
        "Fixture title predicate",
    )

    assert screen.wait.visible(screen.element(), predicate).text == "QA iOS Fixture"


@allure.testcase("IOS-FWK-002")
def test_accessibility_locator_finds_ready_status(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)
    status = IosLocator.accessibility_id("fixture-status", "Ready status")

    assert screen.wait.visible(screen.element(), status).text == "ready"


@allure.testcase("IOS-FWK-003")
def test_class_chain_locator_finds_application_window(
    ios_runtime_driver: Any,
) -> None:
    screen, _ = open_fixture(ios_runtime_driver)

    assert screen.element().is_displayed()


@allure.testcase("IOS-FWK-004")
def test_explicit_wait_finds_file_button(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)
    wait = MobileWait(ios_runtime_driver, WaitPolicy(timeout_seconds=15.0))

    button = wait.visible(screen.element(), FixtureScreen.write_file_button)
    assert button.is_enabled()


@allure.testcase("IOS-FWK-005")
def test_missing_element_timeout_names_locator(ios_runtime_driver: Any) -> None:
    open_fixture(ios_runtime_driver)
    missing = IosLocator.accessibility_id(
        "week21-locator-does-not-exist",
        "Missing Week 21 locator",
    )
    wait = MobileWait(
        ios_runtime_driver,
        WaitPolicy(timeout_seconds=1.0, poll_interval_seconds=0.1),
    )

    with pytest.raises(ElementWaitTimeout) as error:
        wait.visible(ios_runtime_driver, missing)

    assert "week21-locator-does-not-exist" in str(error.value)
    assert "visible" in str(error.value)


@allure.testcase("IOS-FWK-006")
def test_swipe_up_is_accepted_by_xcuitest(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)
    gestures = IosGestures(ios_runtime_driver)

    gestures.swipe(IosSwipeDirection.UP, velocity=0.5)
    assert screen.element().is_displayed()


@allure.testcase("IOS-FWK-007")
def test_swipe_down_restores_initial_region(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)
    gestures = IosGestures(ios_runtime_driver)

    gestures.swipe(IosSwipeDirection.DOWN, velocity=0.5)
    assert screen.wait.visible(screen.element(), FixtureScreen.title).is_displayed()


@allure.testcase("IOS-FWK-008")
def test_scroll_down_keeps_fixture_root(ios_runtime_driver: Any) -> None:
    screen, _ = open_fixture(ios_runtime_driver)
    gestures = IosGestures(ios_runtime_driver)

    gestures.scroll(IosSwipeDirection.DOWN)
    assert screen.element().is_displayed()


@allure.testcase("IOS-FWK-009")
def test_native_context_is_always_available(ios_runtime_driver: Any) -> None:
    open_fixture(ios_runtime_driver)

    assert any("NATIVE_APP" in context.upper() for context in ios_runtime_driver.contexts)


@allure.testcase("IOS-FWK-010")
def test_page_source_is_parseable_xml(ios_runtime_driver: Any) -> None:
    open_fixture(ios_runtime_driver)
    source = ios_runtime_driver.page_source

    tree = ET.fromstring(source)
    assert tree.tag
    assert "fixture-title" in source
