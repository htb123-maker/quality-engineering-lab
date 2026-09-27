"""Unit tests for XCUITest option construction."""

import pytest
from qa_core.config.settings import Settings
from qa_core.driver.ios import build_ios_options


@pytest.mark.unit
def test_ios_options_map_project_settings_to_xcuitest_capabilities() -> None:
    settings = Settings(
        _env_file=None,
        ios_device_name="iPhone 16 Pro",
        ios_platform_version="18.5",
        ios_udid="00000000-0000-0000-0000-000000000000",
        ios_bundle_id="com.example.settings",
        ios_wda_local_port=8101,
        ios_use_new_wda=False,
    )

    capabilities = build_ios_options(settings).to_capabilities()

    assert capabilities["platformName"] == "iOS"
    assert capabilities["appium:automationName"] == "XCUITest"
    assert capabilities["appium:deviceName"] == "iPhone 16 Pro"
    assert capabilities["appium:platformVersion"] == "18.5"
    assert capabilities["appium:udid"] == "00000000-0000-0000-0000-000000000000"
    assert capabilities["appium:bundleId"] == "com.example.settings"
    assert capabilities["appium:noReset"] is True
    assert capabilities["appium:useNewWDA"] is False
    assert capabilities["appium:wdaLocalPort"] == 8101


@pytest.mark.unit
def test_ios_options_omit_optional_runtime_and_udid() -> None:
    settings = Settings(_env_file=None)

    capabilities = build_ios_options(settings).to_capabilities()

    assert "appium:platformVersion" not in capabilities
    assert "appium:udid" not in capabilities
