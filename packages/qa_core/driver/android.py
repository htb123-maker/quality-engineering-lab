"""Android Appium driver creation."""

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.webdriver import WebDriver

from qa_core.config.settings import Settings


def build_android_options(settings: Settings) -> UiAutomator2Options:
    """Build typed UiAutomator2 options from project settings."""

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.udid = settings.android_udid
    options.device_name = settings.android_device_name
    options.platform_version = settings.android_platform_version
    options.app_package = settings.android_app_package
    options.app_activity = settings.android_app_activity
    options.no_reset = True
    return options


def create_android_driver(settings: Settings) -> WebDriver:
    """Create an Appium session against the configured Android device."""

    return webdriver.Remote(
        command_executor=str(settings.appium_server_url).rstrip("/"),
        options=build_android_options(settings),
    )
