"""Android Appium session smoke tests."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import allure
import pytest
from qa_core.config.settings import Settings
from qa_core.driver.android import create_android_driver


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
    require_android_smoke_prerequisites: None,
) -> None:
    del require_android_smoke_prerequisites
    driver = create_android_driver(settings)

    try:
        assert driver.session_id
        assert driver.current_package == settings.android_app_package

        window_size = driver.get_window_size()
        assert window_size["width"] > 0
        assert window_size["height"] > 0
    finally:
        driver.quit()
