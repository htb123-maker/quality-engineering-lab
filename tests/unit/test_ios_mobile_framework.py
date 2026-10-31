"""Unit tests for iOS locators, gestures, keyboard, and screen composition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.mobile.screens import Screen
from qa_core.mobile.waits import MobileWait, SearchContext, WaitPolicy
from qa_core.platforms.ios import (
    IosAlertAction,
    IosGestures,
    IosKeyboard,
    IosLocator,
    IosLocatorStrategy,
    IosSwipeDirection,
    IosSystemAlerts,
)
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement


class FakeNode:
    """Small XCUITest element or driver double."""

    def __init__(
        self,
        *,
        displayed: bool = True,
        children: Mapping[tuple[str, str], FakeNode] | None = None,
    ) -> None:
        self.displayed = displayed
        self.children = dict(children or {})
        self.cleared = 0
        self.typed: list[str] = []
        self.scripts: list[tuple[str, object]] = []
        self.keyboard_hidden = 0

    def find_element(self, by: str, value: str) -> WebElement:
        element = self.children.get((by, value))
        if element is None:
            raise NoSuchElementException(f"missing {by}={value}")
        return cast(WebElement, element)

    def is_displayed(self) -> bool:
        return self.displayed

    def clear(self) -> None:
        self.cleared += 1

    def send_keys(self, value: str) -> None:
        self.typed.append(value)

    def execute_script(self, script: str, argument: object) -> None:
        self.scripts.append((script, argument))

    def hide_keyboard(self) -> None:
        self.keyboard_hidden += 1


class FakeAlert:
    text = "Allow access?"

    def __init__(self) -> None:
        self.accepted = 0
        self.dismissed = 0

    def accept(self) -> None:
        self.accepted += 1

    def dismiss(self) -> None:
        self.dismissed += 1


class FakeSwitchTo:
    def __init__(self, alert: FakeAlert) -> None:
        self.alert = alert


class FakeAlertDriver:
    def __init__(self) -> None:
        self.alert = FakeAlert()
        self.switch_to = FakeSwitchTo(self.alert)


def as_driver(node: FakeNode) -> WebDriver:
    return cast(WebDriver, node)


def as_scope(node: FakeNode) -> SearchContext:
    return cast(SearchContext, node)


def fast_wait_policy() -> WaitPolicy:
    return WaitPolicy(timeout_seconds=0.05, poll_interval_seconds=0.005)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("strategy", "expected_by"),
    [
        (IosLocatorStrategy.ACCESSIBILITY_ID, "accessibility id"),
        (IosLocatorStrategy.PREDICATE, "-ios predicate string"),
        (IosLocatorStrategy.CLASS_CHAIN, "-ios class chain"),
    ],
)
def test_ios_locator_maps_to_xcuitest_strategy(
    strategy: IosLocatorStrategy,
    expected_by: str,
) -> None:
    locator = IosLocator(strategy, "target", "Target")

    assert locator.as_tuple() == (expected_by, "target")
    assert locator.by == expected_by
    assert "Target" in str(locator)


@pytest.mark.unit
def test_ios_locator_rejects_android_only_values() -> None:
    with pytest.raises(ValueError, match="Android-only"):
        IosLocator.accessibility_id("android:id/button1")

    with pytest.raises(ValueError, match="Android-only"):
        IosLocator.predicate("//android.widget.Button")


@pytest.mark.unit
def test_ios_screen_reuses_shared_wait_and_scope() -> None:
    child_locator = IosLocator.accessibility_id("Continue", "Continue button")
    child = FakeNode()
    root = FakeNode(children={child_locator.as_tuple(): child})

    class AppScreen(Screen):
        root_locator = IosLocator.class_chain(
            "**/XCUIElementTypeWindow[1]",
            "App window",
        )

    driver = FakeNode(children={AppScreen.root_locator.as_tuple(): root})
    screen = AppScreen(as_driver(driver), wait_policy=fast_wait_policy()).wait_ready()
    wait = MobileWait(as_driver(driver), fast_wait_policy())

    assert wait.visible(as_scope(root), child_locator) is cast(WebElement, child)
    assert screen.descendant(child_locator) is cast(WebElement, child)


@pytest.mark.unit
def test_ios_gestures_use_semantic_mobile_commands() -> None:
    driver = FakeNode()
    gestures = IosGestures(as_driver(driver))

    gestures.swipe(IosSwipeDirection.UP, velocity=1200)
    gestures.scroll(IosSwipeDirection.DOWN)

    assert driver.scripts == [
        ("mobile: swipe", {"direction": "up", "velocity": 1200}),
        ("mobile: scroll", {"direction": "down"}),
    ]


@pytest.mark.unit
def test_ios_keyboard_types_submits_and_dismisses() -> None:
    driver = FakeNode()
    element = FakeNode()
    keyboard = IosKeyboard(as_driver(driver))

    keyboard.type_text(cast(WebElement, element), "hello")
    keyboard.submit(cast(WebElement, element))
    keyboard.dismiss()

    assert element.cleared == 1
    assert element.typed == ["hello", Keys.RETURN]
    assert driver.keyboard_hidden == 1


@pytest.mark.unit
def test_ios_gestures_reject_invalid_direction_and_velocity() -> None:
    gestures = IosGestures(as_driver(FakeNode()))

    with pytest.raises(TypeError, match="IosSwipeDirection"):
        gestures.swipe(cast(IosSwipeDirection, "up"))

    with pytest.raises(ValueError, match="velocity"):
        gestures.swipe(IosSwipeDirection.UP, velocity=0)


@pytest.mark.unit
def test_ios_system_alerts_accept_and_dismiss() -> None:
    driver = FakeAlertDriver()
    alerts = IosSystemAlerts(cast(WebDriver, driver), timeout_seconds=0.05)

    alerts.handle(IosAlertAction.ACCEPT)
    alerts.handle(IosAlertAction.DISMISS)

    assert driver.alert.accepted == 1
    assert driver.alert.dismissed == 1
