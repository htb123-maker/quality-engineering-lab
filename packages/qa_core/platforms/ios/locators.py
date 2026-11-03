"""Typed locators that preserve iOS-only XCUITest semantics."""

from dataclasses import dataclass
from enum import StrEnum

from appium.webdriver.common.appiumby import AppiumBy

_ANDROID_ONLY_MARKERS = (
    "android:id/",
    "-android uiautomator",
    "//android.",
)


class IosLocatorStrategy(StrEnum):
    """Supported XCUITest locator strategies."""

    ACCESSIBILITY_ID = AppiumBy.ACCESSIBILITY_ID
    PREDICATE = AppiumBy.IOS_PREDICATE
    CLASS_CHAIN = AppiumBy.IOS_CLASS_CHAIN


@dataclass(frozen=True, slots=True)
class IosLocator:
    """One iOS locator with a diagnostic label."""

    strategy: IosLocatorStrategy
    value: str
    description: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, IosLocatorStrategy):
            raise TypeError("locator strategy must be an IosLocatorStrategy")
        if not self.value.strip():
            raise ValueError("locator value must not be empty")
        if self.description is not None and not self.description.strip():
            raise ValueError("locator description must not be empty")
        normalized = self.value.casefold()
        if any(marker in normalized for marker in _ANDROID_ONLY_MARKERS):
            raise ValueError("iOS locators must not use Android-only strategies")

    @classmethod
    def accessibility_id(
        cls,
        value: str,
        description: str | None = None,
    ) -> "IosLocator":
        """Locate by accessibility identifier or label."""

        return cls(IosLocatorStrategy.ACCESSIBILITY_ID, value, description)

    @classmethod
    def predicate(
        cls,
        value: str,
        description: str | None = None,
    ) -> "IosLocator":
        """Locate by an XCUITest predicate expression."""

        return cls(IosLocatorStrategy.PREDICATE, value, description)

    @classmethod
    def class_chain(
        cls,
        value: str,
        description: str | None = None,
    ) -> "IosLocator":
        """Locate by an XCUITest class chain."""

        return cls(IosLocatorStrategy.CLASS_CHAIN, value, description)

    @property
    def by(self) -> str:
        """Return the Appium strategy value."""

        return str(self.strategy)

    def as_tuple(self) -> tuple[str, str]:
        """Return the strategy and value expected by WebDriver."""

        return self.by, self.value

    def __str__(self) -> str:
        label = self.description or self.strategy.name.lower()
        return f"{label} ({self.by}={self.value!r})"
