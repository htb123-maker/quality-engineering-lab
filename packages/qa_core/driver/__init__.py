"""Appium driver factories."""

from qa_core.driver.android import build_android_options, create_android_driver
from qa_core.driver.ios import build_ios_options, create_ios_driver

__all__ = [
    "build_android_options",
    "build_ios_options",
    "create_android_driver",
    "create_ios_driver",
]
