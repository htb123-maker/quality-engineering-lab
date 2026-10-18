"""Android Appium session smoke tests."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import allure
import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings


@allure.epic("Quality Engineering Lab")
@allure.feature("Android Appium")
@allure.story("Session lifecycle")
@pytest.mark.android
@pytest.mark.smoke
@pytest.mark.timeout(300)
@allure.testcase("SMOKE-ANDROID-SESSION-001", "Android session lifecycle")
@allure.link("docs/runbooks/failed-quality-gate.md", name="Failure triage runbook")
def test_android_session_starts_and_quits(
    settings: Settings,
    android_driver: WebDriver,
) -> None:
    driver = android_driver

    assert driver.session_id
    assert driver.current_package == settings.android_app_package

    window_size = driver.get_window_size()
    assert window_size["width"] > 0
    assert window_size["height"] > 0
