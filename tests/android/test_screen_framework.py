"""Android screen, explicit-wait, and gesture smoke tests."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import allure
import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.mobile.locators import Locator, LocatorStrategy
from qa_core.mobile.screens import Screen
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.android.gestures import AndroidGestures, SwipeDirection


class AospHomeScreen(Screen):
    """Minimal screen backed by the AOSP system test app."""

    root_locator = Locator(
        LocatorStrategy.RESOURCE_ID,
        "android:id/content",
        "AOSP home content",
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("Android Appium")
@allure.story("Screen framework")
@pytest.mark.android
@pytest.mark.smoke
@pytest.mark.timeout(300)
@allure.testcase("SMOKE-ANDROID-SCREEN-001", "Android screen and swipe framework")
@allure.link("docs/runbooks/android-locator-and-wait-triage.md", name="Locator triage runbook")
def test_android_screen_waits_and_swipes(
    settings: Settings,
    android_driver: WebDriver,
) -> None:
    driver = android_driver

    wait_policy = WaitPolicy(
        timeout_seconds=settings.android_ui_wait_timeout_seconds,
        poll_interval_seconds=settings.android_ui_wait_poll_seconds,
    )
    screen = AospHomeScreen(driver, wait_policy=wait_policy).wait_ready()
    assert screen.element().is_displayed()

    AndroidGestures(driver).swipe(
        SwipeDirection.UP,
        percent=0.25,
        speed=1_500,
    )

    assert driver.session_id
    assert driver.current_package == settings.android_app_package
