"""iOS Appium driver creation."""

from typing import Any

from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.webdriver import WebDriver

from qa_core.config.settings import Settings

DEFAULT_CLOUD_REMOTE_URLS = {
    "browserstack": "https://hub-cloud.browserstack.com/wd/hub",
    "saucelabs": "https://ondemand.us-west-1.saucelabs.com/wd/hub",
    "lambdatest": "https://mobile-hub.lambdatest.com/wd/hub",
}


def _required_cloud_setting(value: str | None, name: str) -> str:
    """Return a required cloud value without leaking secret values."""

    if value is None or not value.strip():
        raise ValueError(f"missing iOS cloud setting: {name}")
    return value.strip()


def _cloud_capabilities(settings: Settings) -> tuple[str, dict[str, Any], str]:
    """Build the provider-specific options namespace and values."""

    provider = settings.ios_device_provider
    if provider == "local":
        raise ValueError("cloud capabilities require a non-local iOS provider")

    username = _required_cloud_setting(settings.ios_cloud_user, "ios_cloud_user")
    access_key = settings.ios_cloud_access_key
    if access_key is None or not access_key.get_secret_value().strip():
        raise ValueError("missing iOS cloud setting: ios_cloud_access_key")
    app = _required_cloud_setting(settings.ios_cloud_app, "ios_cloud_app")
    common: dict[str, Any] = {
        "deviceName": settings.ios_cloud_device_name,
        "platformVersion": settings.ios_cloud_platform_version,
    }
    secret = access_key.get_secret_value()
    if provider == "browserstack":
        return (
            "bstack:options",
            {
                **common,
                "userName": username,
                "accessKey": secret,
                "projectName": settings.ios_cloud_project_name,
                "buildName": settings.ios_cloud_build_name,
                "sessionName": settings.ios_cloud_session_name,
                "debug": True,
                "networkLogs": True,
            },
            app,
        )
    if provider == "saucelabs":
        return (
            "sauce:options",
            {
                **common,
                "username": username,
                "accessKey": secret,
                "build": settings.ios_cloud_build_name,
                "name": settings.ios_cloud_session_name,
            },
            app,
        )
    return (
        "LT:Options",
        {
            **common,
            "userName": username,
            "accessKey": secret,
            "projectName": settings.ios_cloud_project_name,
            "buildName": settings.ios_cloud_build_name,
            "name": settings.ios_cloud_session_name,
            "isRealMobile": True,
        },
        app,
    )


def _build_cloud_ios_options(settings: Settings) -> XCUITestOptions:
    """Build options for a real iOS device hosted by a vendor cloud."""

    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.automation_name = "XCUITest"
    namespace, capabilities, app = _cloud_capabilities(settings)
    options.set_capability(namespace, capabilities)
    options.app = app
    return options


def build_ios_options(settings: Settings) -> XCUITestOptions:
    """Build typed XCUITest options from project settings."""

    if settings.ios_device_provider != "local":
        return _build_cloud_ios_options(settings)

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

    provider = settings.ios_device_provider
    if provider == "local":
        remote_url = str(settings.appium_server_url)
    elif settings.ios_cloud_remote_url is not None:
        remote_url = str(settings.ios_cloud_remote_url)
    else:
        remote_url = DEFAULT_CLOUD_REMOTE_URLS[provider]

    return webdriver.Remote(
        command_executor=remote_url.rstrip("/"),
        options=build_ios_options(settings),
    )
