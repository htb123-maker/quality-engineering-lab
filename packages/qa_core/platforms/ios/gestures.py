"""XCUITest gesture primitives without screen-size assumptions."""

from enum import StrEnum
from typing import Any

from appium.webdriver.webdriver import WebDriver


class IosSwipeDirection(StrEnum):
    """Directions understood by XCUITest mobile gestures."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class IosGestures:
    """Validated XCUITest swipe and scroll commands."""

    SWIPE_COMMAND = "mobile: swipe"
    SCROLL_COMMAND = "mobile: scroll"

    def __init__(self, driver: WebDriver) -> None:
        self._driver = driver

    def swipe(
        self,
        direction: IosSwipeDirection,
        *,
        velocity: float | None = None,
    ) -> None:
        """Swipe in a semantic direction without hardcoded coordinates."""

        if not isinstance(direction, IosSwipeDirection):
            raise TypeError("direction must be an IosSwipeDirection")
        arguments: dict[str, Any] = {"direction": str(direction)}
        if velocity is not None:
            if velocity <= 0:
                raise ValueError("swipe velocity must be greater than 0")
            arguments["velocity"] = velocity
        self._driver.execute_script(self.SWIPE_COMMAND, arguments)

    def scroll(self, direction: IosSwipeDirection) -> None:
        """Scroll the current page in a semantic direction."""

        if not isinstance(direction, IosSwipeDirection):
            raise TypeError("direction must be an IosSwipeDirection")
        self._driver.execute_script(
            self.SCROLL_COMMAND,
            {"direction": str(direction)},
        )
