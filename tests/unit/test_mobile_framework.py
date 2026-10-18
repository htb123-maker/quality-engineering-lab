"""Unit tests for mobile locator, wait, screen, flow, and gesture primitives."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.mobile.flows import Flow, FlowStep, FlowStepFailure
from qa_core.mobile.locators import Locator, LocatorStrategy
from qa_core.mobile.screens import Screen
from qa_core.mobile.waits import ElementWaitTimeout, MobileWait, SearchContext, WaitPolicy
from qa_core.platforms.android.gestures import AndroidGestures, ScreenRect, SwipeDirection
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.remote.webelement import WebElement


class FakeNode:
    """Small WebDriver/WebElement test double."""

    def __init__(
        self,
        *,
        displayed: bool = True,
        enabled: bool = True,
        text: str = "",
        children: Mapping[tuple[str, str], FakeNode] | None = None,
    ) -> None:
        self.displayed = displayed
        self.enabled = enabled
        self.text = text
        self.children = dict(children or {})
        self.clicks = 0
        self.typed: list[str] = []

    def find_element(self, by: str, value: str) -> WebElement:
        element = self.children.get((by, value))
        if element is None:
            raise NoSuchElementException(f"missing {by}={value}")
        return cast(WebElement, element)

    def is_displayed(self) -> bool:
        return self.displayed

    def is_enabled(self) -> bool:
        return self.enabled

    def click(self) -> None:
        self.clicks += 1

    def clear(self) -> None:
        self.text = ""

    def send_keys(self, value: str) -> None:
        self.typed.append(value)
        self.text += value

    def get_attribute(self, name: str) -> str | None:
        return {"content-desc": self.text}.get(name)


def as_driver(node: FakeNode) -> WebDriver:
    """Cast a test double at the WebDriver boundary."""

    return cast(WebDriver, node)


def as_scope(node: FakeNode) -> SearchContext:
    """Cast a test double at the element-search boundary."""

    return cast(SearchContext, node)


def fast_wait_policy() -> WaitPolicy:
    """Keep timeout tests fast without changing production defaults."""

    return WaitPolicy(timeout_seconds=0.05, poll_interval_seconds=0.005)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("strategy", "expected_by"),
    [
        (LocatorStrategy.ACCESSIBILITY_ID, "accessibility id"),
        (LocatorStrategy.RESOURCE_ID, "id"),
        (LocatorStrategy.UIAUTOMATOR, "-android uiautomator"),
        (LocatorStrategy.XPATH, "xpath"),
    ],
)
def test_locator_maps_to_appium_strategy(
    strategy: LocatorStrategy,
    expected_by: str,
) -> None:
    locator = Locator(strategy, "target")

    assert locator.as_tuple() == (expected_by, "target")
    assert locator.by == expected_by


@pytest.mark.unit
def test_locator_rejects_empty_value_and_invalid_strategy() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Locator(LocatorStrategy.RESOURCE_ID, " ")

    with pytest.raises(TypeError, match="LocatorStrategy"):
        Locator(cast(LocatorStrategy, "id"), "target")


@pytest.mark.unit
def test_mobile_wait_resolves_visible_and_clickable_elements() -> None:
    locator = Locator(LocatorStrategy.ACCESSIBILITY_ID, "Continue")
    element = FakeNode(text="Continue")
    scope = FakeNode(children={locator.as_tuple(): element})
    wait = MobileWait(as_driver(scope), fast_wait_policy())

    assert wait.visible(as_scope(scope), locator) is cast(WebElement, element)
    assert wait.clickable(as_scope(scope), locator) is cast(WebElement, element)
    assert wait.present(as_scope(scope), locator) is cast(WebElement, element)


@pytest.mark.unit
def test_mobile_wait_timeout_names_locator_and_expected_state() -> None:
    locator = Locator(
        LocatorStrategy.RESOURCE_ID,
        "com.example:id/submit",
        "Submit button",
    )
    wait = MobileWait(as_driver(FakeNode()), fast_wait_policy())

    with pytest.raises(ElementWaitTimeout) as error:
        wait.visible(as_scope(FakeNode()), locator)

    assert error.value.locator is locator
    assert error.value.expected_state == "visible"
    assert "Submit button" in str(error.value)


@pytest.mark.unit
def test_mobile_wait_gone_succeeds_when_element_is_missing() -> None:
    locator = Locator(LocatorStrategy.ACCESSIBILITY_ID, "Loading")
    wait = MobileWait(as_driver(FakeNode()), fast_wait_policy())

    wait.gone(as_scope(FakeNode()), locator)


@pytest.mark.unit
def test_screen_scopes_descendants_and_actions_to_its_root() -> None:
    screen_root_locator = Locator(LocatorStrategy.RESOURCE_ID, "android:id/content")
    child_locator = Locator(LocatorStrategy.ACCESSIBILITY_ID, "Continue")
    child = FakeNode(text="Continue")
    root = FakeNode(children={child_locator.as_tuple(): child})
    driver = FakeNode(children={screen_root_locator.as_tuple(): root})

    class TestScreen(Screen):
        root_locator = screen_root_locator

    screen = TestScreen(as_driver(driver), wait_policy=fast_wait_policy()).wait_ready()

    assert screen.element() is cast(WebElement, root)
    assert screen.text_of(child_locator) == "Continue"
    assert screen.attribute_of(child_locator, "content-desc") == "Continue"
    screen.send_keys(child_locator, "next")
    assert child.typed == ["next"]
    screen.tap(child_locator)
    assert child.clicks == 1


class FakeGestureDriver:
    """Record UiAutomator2 mobile commands."""

    def __init__(self) -> None:
        self.scripts: list[tuple[str, object]] = []

    def get_window_size(self) -> dict[str, int]:
        return {"width": 1080, "height": 2400}

    def execute_script(self, script: str, argument: object) -> object:
        self.scripts.append((script, argument))
        return None


@pytest.mark.unit
def test_android_swipe_uses_the_full_window_and_explicit_parameters() -> None:
    driver = FakeGestureDriver()
    gestures = AndroidGestures(cast(WebDriver, driver))

    gestures.swipe(
        SwipeDirection.UP,
        percent=0.4,
        speed=2_000,
    )

    assert driver.scripts == [
        (
            "mobile: swipeGesture",
            {
                "left": 0,
                "top": 0,
                "width": 1080,
                "height": 2400,
                "direction": "up",
                "percent": 0.4,
                "speed": 2_000,
            },
        )
    ]


@pytest.mark.unit
def test_android_swipe_rejects_invalid_percent_and_rectangle() -> None:
    gestures = AndroidGestures(cast(WebDriver, FakeGestureDriver()))

    with pytest.raises(ValueError, match="percent"):
        gestures.swipe(SwipeDirection.LEFT, percent=0)

    with pytest.raises(ValueError, match="positive dimensions"):
        ScreenRect(left=0, top=0, width=0, height=100)


@pytest.mark.unit
def test_flow_runs_steps_in_order_and_returns_final_state() -> None:
    flow = Flow[int](
        "Counter",
        [
            FlowStep("add one", lambda value: value + 1),
            FlowStep("double", lambda value: value * 2),
        ],
    )

    assert flow.run(3) == 8


@pytest.mark.unit
def test_flow_failure_identifies_step_and_preserves_cause() -> None:
    cause = RuntimeError("element disappeared")

    def fail_after_transition(value: int) -> int:
        if value == 1:
            raise cause
        return value

    flow = Flow[int](
        "Checkout",
        [
            FlowStep("open cart", lambda value: value + 1),
            FlowStep("submit order", fail_after_transition),
        ],
    )

    with pytest.raises(FlowStepFailure) as error:
        flow.run(0)

    assert error.value.flow_name == "Checkout"
    assert error.value.step_index == 1
    assert error.value.step_name == "submit order"
    assert error.value.cause is cause
    assert error.value.__cause__ is cause


@pytest.mark.unit
def test_flow_rejects_duplicate_step_names() -> None:
    with pytest.raises(ValueError, match="unique"):
        Flow[int](
            "Duplicate",
            [
                FlowStep("same", lambda value: value),
                FlowStep("same", lambda value: value),
            ],
        )
