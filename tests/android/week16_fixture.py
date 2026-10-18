"""Week 16 fixture screen and deterministic reset helpers."""

from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.mobile.locators import Locator, LocatorStrategy
from qa_core.mobile.screens import Screen
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.android import AndroidActivities, AndroidIntent

from tests.android.conftest import FIXTURE_ACTIVITY, FIXTURE_PACKAGE

TITLE = Locator(LocatorStrategy.ACCESSIBILITY_ID, "fixture-title", "Fixture title")
STATUS = Locator(LocatorStrategy.ACCESSIBILITY_ID, "fixture-status", "Fixture status")
RESUME = Locator(LocatorStrategy.ACCESSIBILITY_ID, "fixture-resume", "Resume counter")
INPUT = Locator(LocatorStrategy.ACCESSIBILITY_ID, "fixture-input", "Fixture input")
SUBMIT = Locator(LocatorStrategy.ACCESSIBILITY_ID, "fixture-submit", "Form submit")
RESET = Locator(LocatorStrategy.ACCESSIBILITY_ID, "fixture-reset", "Form reset")
FORM_STATUS = Locator(
    LocatorStrategy.ACCESSIBILITY_ID,
    "fixture-form-status",
    "Form status",
)
COUNTER = Locator(LocatorStrategy.ACCESSIBILITY_ID, "fixture-counter", "Counter button")
COUNTER_VALUE = Locator(
    LocatorStrategy.ACCESSIBILITY_ID,
    "fixture-counter-value",
    "Counter value",
)
MODAL = Locator(LocatorStrategy.ACCESSIBILITY_ID, "fixture-modal", "Open dialog")
CAMERA = Locator(LocatorStrategy.ACCESSIBILITY_ID, "request-camera", "Request camera")
DIALOG_TITLE = Locator(
    LocatorStrategy.UIAUTOMATOR,
    'new UiSelector().text("Fixture dialog")',
    "Fixture dialog title",
)
DIALOG_CONFIRM = Locator(
    LocatorStrategy.RESOURCE_ID,
    "android:id/button1",
    "Dialog confirm",
)
DIALOG_CANCEL = Locator(
    LocatorStrategy.RESOURCE_ID,
    "android:id/button2",
    "Dialog cancel",
)


def fixture_wait_policy(settings: Settings) -> WaitPolicy:
    """Build the bounded wait policy used by fixture tests."""

    return WaitPolicy(
        timeout_seconds=settings.android_ui_wait_timeout_seconds,
        poll_interval_seconds=settings.android_ui_wait_poll_seconds,
    )


class FixtureScreen(Screen):
    """Main screen exposed by the dependency-free Android fixture."""

    root_locator = Locator(
        LocatorStrategy.RESOURCE_ID,
        "android:id/content",
        "Android fixture root",
    )


def reset_fixture_app(driver: WebDriver, settings: Settings) -> FixtureScreen:
    """Restart the fixture Activity so every test starts from clean app state."""

    component = f"{FIXTURE_PACKAGE}/{FIXTURE_ACTIVITY}"
    activities = AndroidActivities(driver, fixture_wait_policy(settings))
    activities.start(
        AndroidIntent(
            action="android.intent.action.MAIN",
            component=component,
            stop=True,
        )
    )
    return FixtureScreen(
        driver,
        wait_policy=fixture_wait_policy(settings),
    ).wait_ready()
