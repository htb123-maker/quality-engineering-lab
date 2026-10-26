"""iOS Appium driver creation."""

from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.webdriver import WebDriver

from qa_core.config.settings import Settings


def build_ios_options(settings: Settings) -> XCUITestOptions:
    """Build typed XCUITest options from project settings."""

    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.automation_name = "XCUITest"
    options.device_name = settings.ios_device_name
    if settings.ios_platform_version:
        options.platform_version = settings.ios_platform_version
    if settings.ios_udid:
        options.udid = settings.ios_udid
    options.bundle_id = settings.ios_bundle_id
    if settings.ios_xcode_org_id:
        options.xcode_org_id = settings.ios_xcode_org_id
        options.xcode_signing_id = settings.ios_xcode_signing_id
    if settings.ios_updated_wda_bundle_id:
        options.updated_wda_bundle_id = settings.ios_updated_wda_bundle_id
    if settings.ios_allow_provisioning_updates:
        options.set_capability("appium:allowProvisioningUpdates", True)
    options.show_xcode_log = settings.ios_show_xcode_log
    options.no_reset = True
    options.use_new_wda = settings.ios_use_new_wda
    options.wda_local_port = settings.ios_wda_local_port
    options.wda_launch_timeout = settings.ios_wda_launch_timeout_ms
    options.wda_startup_retries = settings.ios_wda_startup_retries
    options.wda_startup_retry_interval = settings.ios_wda_startup_retry_interval_ms
    return options


def create_ios_driver(settings: Settings) -> WebDriver:
    """Create an Appium session against the configured iOS Simulator or device."""

    return webdriver.Remote(
        command_executor=str(settings.appium_server_url).rstrip("/"),
        options=build_ios_options(settings),
    )
