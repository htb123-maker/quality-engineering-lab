"""UiAutomator2 gesture primitives."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from appium.webdriver.webdriver import WebDriver


class SwipeDirection(StrEnum):
    """Directions understood by the UiAutomator2 swipe gesture."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class ScreenRect:
    """Pixel rectangle used as a gesture boundary."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0:
            raise ValueError("gesture origin must not be negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("gesture rectangle must have positive dimensions")

    @classmethod
    def from_window_size(cls, size: Mapping[str, int]) -> "ScreenRect":
        """Build a full-window rectangle from WebDriver window dimensions."""

        width = size.get("width")
        height = size.get("height")
        if width is None or height is None:
            raise ValueError("window size must include width and height")
        return cls(left=0, top=0, width=width, height=height)


class AndroidGestures:
    """Explicit UiAutomator2 gestures with validated arguments."""

    SWIPE_COMMAND = "mobile: swipeGesture"

    def __init__(self, driver: WebDriver) -> None:
        self._driver = driver

    def swipe(
        self,
        direction: SwipeDirection,
        *,
        area: ScreenRect | None = None,
        percent: float = 0.6,
        speed: int = 5_000,
    ) -> None:
        """Swipe within the screen or a supplied rectangle."""

        if not isinstance(direction, SwipeDirection):
            raise TypeError("direction must be a SwipeDirection")
        if not 0.0 < percent <= 1.0:
            raise ValueError("swipe percent must be greater than 0 and at most 1")
        if speed <= 0:
            raise ValueError("swipe speed must be greater than 0")

        bounds = area or ScreenRect.from_window_size(self._driver.get_window_size())
        self._driver.execute_script(
            self.SWIPE_COMMAND,
            {
                "left": bounds.left,
                "top": bounds.top,
                "width": bounds.width,
                "height": bounds.height,
                "direction": str(direction),
                "percent": percent,
                "speed": speed,
            },
        )
