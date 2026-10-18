"""Typed locators with an explicit strategy and diagnostic label."""

from dataclasses import dataclass
from enum import StrEnum

from appium.webdriver.common.appiumby import AppiumBy


class LocatorStrategy(StrEnum):
    """Supported Android Appium locator strategies."""

    ACCESSIBILITY_ID = AppiumBy.ACCESSIBILITY_ID
    RESOURCE_ID = AppiumBy.ID
    UIAUTOMATOR = AppiumBy.ANDROID_UIAUTOMATOR
    XPATH = AppiumBy.XPATH


@dataclass(frozen=True, slots=True)
class Locator:
    """One typed locator that can travel through screens and components."""

    strategy: LocatorStrategy
    value: str
    description: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, LocatorStrategy):
            raise TypeError("locator strategy must be a LocatorStrategy")
        if not self.value.strip():
            raise ValueError("locator value must not be empty")
        if self.description is not None and not self.description.strip():
            raise ValueError("locator description must not be empty")

    @property
    def by(self) -> str:
        """Return the Appium/Selenium strategy value."""

        return str(self.strategy)

    def as_tuple(self) -> tuple[str, str]:
        """Return the strategy and value expected by WebDriver find methods."""

        return self.by, self.value

    def __str__(self) -> str:
        label = self.description or self.strategy.name.lower()
        return f"{label} ({self.by}={self.value!r})"
