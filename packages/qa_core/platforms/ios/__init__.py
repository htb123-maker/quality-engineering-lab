"""iOS-specific Appium framework primitives."""

from qa_core.platforms.ios.gestures import IosGestures, IosSwipeDirection
from qa_core.platforms.ios.keyboard import IosKeyboard
from qa_core.platforms.ios.locators import IosLocator, IosLocatorStrategy

__all__ = [
    "IosGestures",
    "IosKeyboard",
    "IosLocator",
    "IosLocatorStrategy",
    "IosSwipeDirection",
]
