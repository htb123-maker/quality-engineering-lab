"""Real-device cloud Appium session smoke."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import os

import allure
import pytest
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver

CLOUD_PROVIDERS = {"browserstack", "saucelabs", "lambdatest"}


@allure.epic("Quality Engineering Lab")
@allure.feature("iOS Cloud Device")
@allure.story("Cloud session lifecycle")
@pytest.mark.ios
@pytest.mark.smoke
@pytest.mark.skipif(
    os.getenv("QA_IOS_DEVICE_PROVIDER", "local").lower() not in CLOUD_PROVIDERS,
    reason="iOS cloud provider is not configured.",
)
@pytest.mark.timeout(900)
@allure.testcase("SMOKE-IOS-CLOUD-001", "iOS cloud session lifecycle")
@allure.link("docs/runbooks/ios-cloud-device-provider.md", name="Cloud runbook")
def test_cloud_ios_session_starts_and_quits(settings: Settings) -> None:
    driver = create_ios_driver(settings)

    try:
        assert driver.session_id
        assert str(driver.capabilities.get("platformName", "")).lower() == "ios"
        window_size = driver.get_window_size()
        assert window_size["width"] > 0
        assert window_size["height"] > 0
    finally:
        driver.quit()
