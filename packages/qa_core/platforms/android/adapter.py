"""Android implementation of the shared fixture adapter contract."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from appium.webdriver.webdriver import WebDriver

from qa_core.mobile.diagnostics import MobileDiagnostics, MobileFailureEvidence
from qa_core.mobile.locators import Locator, LocatorStrategy
from qa_core.mobile.platforms import (
    LocatorSet,
    MobilePlatform,
    NavigationOutcome,
    PlatformCapability,
)
from qa_core.mobile.waits import MobileWait, WaitPolicy
from qa_core.platforms.android.activities import AndroidActivities, AndroidIntent
from qa_core.platforms.android.files import AndroidFiles


class AndroidFixtureFilePort:
    """Android device-file implementation of the shared file port."""

    def __init__(self, driver: WebDriver) -> None:
        self._files = AndroidFiles(driver)
        self._remote_path: str | None = None

    def write_text(self, content: str) -> None:
        self.cleanup()
        self._remote_path = AndroidFiles.temporary_path()
        self._files.write_text(self._remote_path, content)

    def read_text(self) -> str:
        if self._remote_path is None:
            raise RuntimeError("fixture file has not been written")
        return self._files.read_text(self._remote_path)

    def cleanup(self) -> None:
        if self._remote_path is None:
            return
        path = self._remote_path
        self._remote_path = None
        if self._files.exists(path):
            self._files.delete(path)


class AndroidFixtureAdapter:
    """Cross-platform fixture operations backed by UiAutomator2."""

    def __init__(
        self,
        driver: WebDriver,
        *,
        component: str,
        wait_policy: WaitPolicy | None = None,
        diagnostics_directory: Path | None = None,
    ) -> None:
        if "/" not in component:
            raise ValueError("Android component must use package/activity form")
        self._driver = driver
        self._component = component
        self._policy = wait_policy or WaitPolicy()
        self._activities = AndroidActivities(driver, self._policy)
        self._wait = MobileWait(driver, self._policy)
        self._files = AndroidFixtureFilePort(driver)
        self._diagnostics = (
            MobileDiagnostics(driver, diagnostics_directory)
            if diagnostics_directory is not None
            else None
        )
        self._locators = LocatorSet(
            MobilePlatform.ANDROID,
            {
                "fixture.root": Locator(
                    LocatorStrategy.RESOURCE_ID,
                    "android:id/content",
                    "Android fixture root",
                ),
                "fixture.title": Locator(
                    LocatorStrategy.ACCESSIBILITY_ID,
                    "fixture-title",
                    "Android fixture title",
                ),
                "fixture.navigation_button": Locator(
                    LocatorStrategy.ACCESSIBILITY_ID,
                    "fixture-navigation",
                    "Android fixture navigation button",
                ),
                "fixture.navigation_status": Locator(
                    LocatorStrategy.UIAUTOMATOR,
                    'new UiSelector().descriptionStartsWith("fixture-status:deep-link:")',
                    "Android fixture navigation status",
                ),
            },
        )

    @property
    def platform(self) -> MobilePlatform:
        return MobilePlatform.ANDROID

    @property
    def capabilities(self) -> frozenset[PlatformCapability]:
        return frozenset(
            {
                PlatformCapability.NAVIGATION,
                PlatformCapability.FILES,
                PlatformCapability.DIAGNOSTICS,
            }
        )

    @property
    def locators(self) -> LocatorSet:
        return self._locators

    @property
    def files(self) -> AndroidFixtureFilePort:
        return self._files

    def launch_fixture(self) -> None:
        self._activities.start(
            AndroidIntent(
                action="android.intent.action.MAIN",
                component=self._component,
                stop=True,
            )
        )
        self._wait.visible(self._driver, self.locators.get("fixture.root"))
        title = self._wait.visible(
            self._driver,
            self.locators.get("fixture.title"),
        )
        if not title.text.strip():
            raise RuntimeError("Android fixture title must not be empty")

    def tap(self, locator_key: str) -> None:
        self._wait.clickable(
            self._driver,
            self.locators.get(locator_key),
        ).click()

    def text(self, locator_key: str) -> str:
        return self._wait.visible(
            self._driver,
            self.locators.get(locator_key),
        ).text

    def trigger_navigation(self) -> NavigationOutcome:
        deep_link = "qaweek15://permission/week22"
        self._activities.start(
            AndroidIntent(
                action="android.intent.action.VIEW",
                uri=deep_link,
                component=self._component,
                stop=True,
            )
        )
        status = self._wait.visible(
            self._driver,
            self.locators.get("fixture.navigation_status"),
        )
        if deep_link not in status.text:
            raise RuntimeError(
                f"Android navigation status did not contain {deep_link!r}: "
                f"{status.text!r}"
            )
        return NavigationOutcome.COMPLETED

    def capture_failure(
        self,
        *,
        scenario_id: str,
        step_id: str,
        error: BaseException,
        context: Mapping[str, object] | None = None,
    ) -> MobileFailureEvidence | None:
        if self._diagnostics is None:
            return None
        payload: dict[str, object] = {
            "platform": self.platform.value,
            "component": self._component,
        }
        payload.update(context or {})
        return self._diagnostics.capture_failure(
            scenario_id=scenario_id,
            step_id=step_id,
            error=error,
            context=payload,
        )
