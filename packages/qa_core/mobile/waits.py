"""Bounded explicit waits and diagnostics for mobile elements."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar, cast

from appium.webdriver.webdriver import WebDriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from qa_core.mobile.locators import Locator

ResultT = TypeVar("ResultT")


class SearchContext(Protocol):
    """A driver or element that can resolve a child locator."""

    def find_element(self, by: str, value: str) -> WebElement:
        """Resolve one direct child element."""


@dataclass(frozen=True, slots=True)
class WaitPolicy:
    """Deadline and polling interval for one explicit wait."""

    timeout_seconds: float = 10.0
    poll_interval_seconds: float = 0.25

    def __post_init__(self) -> None:
        if not 0.0 < self.timeout_seconds <= 600.0:
            raise ValueError("wait timeout must be greater than 0 and at most 600 seconds")
        if not 0.0 < self.poll_interval_seconds <= self.timeout_seconds:
            raise ValueError("poll interval must be greater than 0 and no longer than timeout")


class ElementWaitTimeout(TimeoutError):
    """Explicit-wait timeout that names the element and expected state."""

    def __init__(
        self,
        locator: Locator,
        expected_state: str,
        timeout_seconds: float,
    ) -> None:
        self.locator = locator
        self.expected_state = expected_state
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Timed out after {timeout_seconds:.2f}s waiting for {locator} "
            f"to be {expected_state}"
        )


class MobileWait:
    """WebDriverWait wrapper with mobile-specific element states."""

    def __init__(
        self,
        driver: WebDriver,
        policy: WaitPolicy | None = None,
    ) -> None:
        self.policy = policy or WaitPolicy()
        self._driver_wait: WebDriverWait[WebDriver] = WebDriverWait(
            driver,
            timeout=self.policy.timeout_seconds,
            poll_frequency=self.policy.poll_interval_seconds,
            ignored_exceptions=(
                NoSuchElementException,
                StaleElementReferenceException,
            ),
        )

    def _until(
        self,
        locator: Locator,
        expected_state: str,
        predicate: Callable[[], ResultT | bool],
    ) -> ResultT | bool:
        message = f"waiting for {locator} to be {expected_state}"
        try:
            return cast(
                ResultT | bool,
                self._driver_wait.until(lambda _: predicate(), message=message),
            )
        except TimeoutException as exc:
            raise ElementWaitTimeout(
                locator,
                expected_state,
                self.policy.timeout_seconds,
            ) from exc

    def visible(self, scope: SearchContext, locator: Locator) -> WebElement:
        """Wait until the element exists and is displayed."""

        def find_visible() -> WebElement | bool:
            element = scope.find_element(*locator.as_tuple())
            return element if element.is_displayed() else False

        return cast(
            WebElement,
            self._until(locator, "visible", find_visible),
        )

    def present(self, scope: SearchContext, locator: Locator) -> WebElement:
        """Wait until the element exists in the current UI hierarchy."""

        return cast(
            WebElement,
            self._until(
                locator,
                "present",
                lambda: scope.find_element(*locator.as_tuple()),
            ),
        )

    def clickable(self, scope: SearchContext, locator: Locator) -> WebElement:
        """Wait until the element is displayed and enabled."""

        def find_clickable() -> WebElement | bool:
            element = scope.find_element(*locator.as_tuple())
            return element if element.is_displayed() and element.is_enabled() else False

        return cast(
            WebElement,
            self._until(locator, "clickable", find_clickable),
        )

    def gone(self, scope: SearchContext, locator: Locator) -> None:
        """Wait until the element no longer exists in the current hierarchy."""

        def missing() -> bool:
            try:
                scope.find_element(*locator.as_tuple())
            except NoSuchElementException:
                return True
            return False

        self._until(locator, "gone", missing)
