"""iOS Appium session smoke tests."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import sys

import allure
import pytest
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver


@allure.epic("Quality Engineering Lab")
@allure.feature("iOS Appium")
@allure.story("Session lifecycle")
@pytest.mark.ios
@pytest.mark.smoke
@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="XCUITest requires macOS, Xcode, and WebDriverAgent.",
)
@pytest.mark.timeout(600)
def test_ios_session_starts_and_quits(settings: Settings) -> None:
    driver = create_ios_driver(settings)

    try:
        assert driver.session_id
        assert str(driver.capabilities.get("platformName", "")).lower() == "ios"

        window_size = driver.get_window_size()
        assert window_size["width"] > 0
        assert window_size["height"] > 0
    finally:
        driver.quit()
