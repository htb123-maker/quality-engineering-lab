"""Explicit iOS keyboard interactions."""

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement


class IosKeyboard:
    """Type, submit, and dismiss the iOS keyboard without fixed sleeps."""

    def __init__(self, driver: WebDriver) -> None:
        self._driver = driver

    def type_text(
        self,
        element: WebElement,
        value: str,
        *,
        clear: bool = True,
    ) -> None:
        """Enter text into a focused or resolvable input element."""

        if clear:
            element.clear()
        element.send_keys(value)

    def submit(self, element: WebElement) -> None:
        """Send Return through the current input element."""

        element.send_keys(Keys.RETURN)

    def dismiss(self) -> None:
        """Dismiss the visible keyboard through XCUITest."""

        self._driver.hide_keyboard()
