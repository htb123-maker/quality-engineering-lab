"""Unit tests for XCUITest option construction."""

from unittest.mock import Mock

import pytest
from qa_core.config.settings import Settings
from qa_core.driver.ios import build_ios_options, create_ios_driver


@pytest.mark.unit
def test_ios_options_map_project_settings_to_xcuitest_capabilities() -> None:
    settings = Settings(
        _env_file=None,
        ios_device_name="iPhone 16 Pro",
        ios_platform_version="18.5",
        ios_udid="00000000-0000-0000-0000-000000000000",
        ios_bundle_id="com.example.settings",
        ios_xcode_org_id="TEAM123456",
        ios_xcode_signing_id="Apple Development",
        ios_updated_wda_bundle_id="com.example.qa.WebDriverAgentRunner",
        ios_allow_provisioning_updates=True,
        ios_show_xcode_log=True,
        ios_wda_local_port=8101,
        ios_use_new_wda=False,
        ios_wda_launch_timeout_ms=300_000,
        ios_wda_startup_retries=1,
        ios_wda_startup_retry_interval_ms=5_000,
    )

    capabilities = build_ios_options(settings).to_capabilities()

    assert capabilities["platformName"] == "iOS"
    assert capabilities["appium:automationName"] == "XCUITest"
    assert capabilities["appium:deviceName"] == "iPhone 16 Pro"
    assert capabilities["appium:platformVersion"] == "18.5"
    assert capabilities["appium:udid"] == "00000000-0000-0000-0000-000000000000"
    assert capabilities["appium:bundleId"] == "com.example.settings"
    assert capabilities["appium:xcodeOrgId"] == "TEAM123456"
    assert capabilities["appium:xcodeSigningId"] == "Apple Development"
    assert (
        capabilities["appium:updatedWDABundleId"]
        == "com.example.qa.WebDriverAgentRunner"
    )
    assert capabilities["appium:allowProvisioningUpdates"] is True
    assert capabilities["appium:showXcodeLog"] is True
    assert capabilities["appium:noReset"] is True
    assert capabilities["appium:useNewWDA"] is False
    assert capabilities["appium:wdaLocalPort"] == 8101
    assert capabilities["appium:wdaLaunchTimeout"] == 300_000
    assert capabilities["appium:wdaStartupRetries"] == 1
    assert capabilities["appium:wdaStartupRetryInterval"] == 5_000


@pytest.mark.unit
def test_ios_options_omit_optional_runtime_and_udid() -> None:
    settings = Settings(_env_file=None)

    capabilities = build_ios_options(settings).to_capabilities()

    assert "appium:platformVersion" not in capabilities
    assert "appium:udid" not in capabilities
    assert "appium:xcodeOrgId" not in capabilities
    assert "appium:updatedWDABundleId" not in capabilities


def test_browserstack_options_use_nested_vendor_capabilities() -> None:
    settings = Settings(
        _env_file=None,
        ios_device_provider="browserstack",
        ios_cloud_user="cloud-user",
        ios_cloud_access_key="cloud-secret",
        ios_cloud_app="bs://example-app",
        ios_cloud_device_name="iPhone 15",
        ios_cloud_platform_version="17",
    )

    capabilities = build_ios_options(settings).to_capabilities()
    vendor_options = capabilities["bstack:options"]

    assert vendor_options["userName"] == "cloud-user"
    assert vendor_options["accessKey"] == "cloud-secret"
    assert vendor_options["app"] == "bs://example-app"
    assert vendor_options["deviceName"] == "iPhone 15"
    assert vendor_options["platformVersion"] == "17"
    assert vendor_options["networkLogs"] is True
    assert "cloud-secret" not in repr(settings)


@pytest.mark.parametrize(
    ("provider", "namespace"),
    [
        ("saucelabs", "sauce:options"),
        ("lambdatest", "LT:Options"),
    ],
)
def test_other_cloud_providers_map_to_their_namespace(
    provider: str,
    namespace: str,
) -> None:
    settings = Settings(
        _env_file=None,
        ios_device_provider=provider,
        ios_cloud_user="cloud-user",
        ios_cloud_access_key="cloud-secret",
        ios_cloud_app="storage:example-app",
    )

    capabilities = build_ios_options(settings).to_capabilities()

    assert capabilities[namespace]["accessKey"] == "cloud-secret"
    assert capabilities[namespace]["app"] == "storage:example-app"


def test_cloud_provider_requires_credentials_and_app() -> None:
    settings = Settings(_env_file=None, ios_device_provider="browserstack")

    with pytest.raises(ValueError, match="ios_cloud_user"):
        build_ios_options(settings)


def test_create_cloud_driver_uses_default_provider_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = Mock()
    monkeypatch.setattr("qa_core.driver.ios.webdriver.Remote", remote)
    settings = Settings(
        _env_file=None,
        ios_device_provider="browserstack",
        ios_cloud_user="cloud-user",
        ios_cloud_access_key="cloud-secret",
        ios_cloud_app="bs://example-app",
    )

    create_ios_driver(settings)

    assert remote.call_args.kwargs["command_executor"] == (
        "https://hub-cloud.browserstack.com/wd/hub"
    )
