"""Screen and component composition for mobile tests."""

from __future__ import annotations

from typing import Self

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from qa_core.mobile.locators import Locator
from qa_core.mobile.waits import MobileWait, SearchContext, WaitPolicy


class Component:
    """A reusable UI region scoped to a root locator."""

    root_locator: Locator

    def __init__(
        self,
        driver: WebDriver,
        *,
        parent: Component | None = None,
        wait_policy: WaitPolicy | None = None,
    ) -> None:
        self.driver = driver
        self.parent = parent
        self.wait = MobileWait(driver, wait_policy)

    def scope(self) -> SearchContext:
        """Return the parent element or driver used by this component."""

        return self.parent.element() if self.parent is not None else self.driver

    def element(self) -> WebElement:
        """Resolve this component's root element."""

        return self.wait.visible(self.scope(), self.root_locator)

    def descendant(self, locator: Locator) -> WebElement:
        """Resolve a visible element inside this component only."""

        return self.wait.visible(self.element(), locator)

    def tap(self, locator: Locator) -> None:
        """Tap one clickable descendant."""

        self.wait.clickable(self.element(), locator).click()

    def text_of(self, locator: Locator) -> str:
        """Return the displayed text of a descendant."""

        return self.descendant(locator).text

    def send_keys(self, locator: Locator, value: str) -> None:
        """Clear and type into a descendant input."""

        element = self.descendant(locator)
        element.clear()
        element.send_keys(value)

    def attribute_of(self, locator: Locator, name: str) -> str | None:
        """Read one WebDriver attribute from a descendant."""

        return self.descendant(locator).get_attribute(name)


class Screen(Component):
    """A full screen (page) with a required visible root element."""

    def wait_ready(self) -> Self:
        """Block until the screen root is visible."""

        self.element()
        return self
