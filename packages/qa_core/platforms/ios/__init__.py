"""iOS-specific Appium framework primitives."""

from qa_core.platforms.ios.gestures import IosGestures, IosSwipeDirection
from qa_core.platforms.ios.keyboard import IosKeyboard
from qa_core.platforms.ios.locators import IosLocator, IosLocatorStrategy
from qa_core.platforms.ios.permissions import (
    IosAlertAction,
    IosAlertTimeout,
    IosSystemAlerts,
)

__all__ = [
    "IosAlertAction",
    "IosAlertTimeout",
    "IosGestures",
    "IosKeyboard",
    "IosLocator",
    "IosLocatorStrategy",
    "IosSwipeDirection",
    "IosSystemAlerts",
]
