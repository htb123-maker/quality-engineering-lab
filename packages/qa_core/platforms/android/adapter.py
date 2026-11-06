"""Android implementation of the shared fixture adapter contract."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping
from pathlib import Path

from appium.webdriver.webdriver import WebDriver

from qa_core.mobile.diagnostics import MobileDiagnostics, MobileFailureEvidence
from qa_core.mobile.locators import Locator, LocatorStrategy
from qa_core.mobile.platforms import (
    CatalogSnapshot,
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


class AndroidFixtureCatalogPort:
    """API-backed catalog operations implemented by the Android fixture."""

    def __init__(self, adapter: AndroidFixtureAdapter) -> None:
        self._adapter = adapter

    def open(self, *, base_url: str, session_id: str) -> CatalogSnapshot:
        payload = base64.urlsafe_b64encode(
            json.dumps(
                {"e2eBaseUrl": base_url, "sessionId": session_id},
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).decode("ascii").rstrip("=")
        deep_link = f"qaweek15://e2e/{payload}"
        self._adapter._activities.start(  # noqa: SLF001 - same package boundary
            AndroidIntent(
                action="android.intent.action.VIEW",
                uri=deep_link,
                component=self._adapter._component,  # noqa: SLF001
                stop=True,
            )
        )
        self._adapter.catalog_session_id = session_id
        return self._adapter.wait_catalog_snapshot(session_id)

    def archive(self) -> CatalogSnapshot:
        self._adapter.tap("fixture.catalog_archive")
        return self._adapter.wait_catalog_snapshot(self._adapter.catalog_session_id)


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
        self._catalog = AndroidFixtureCatalogPort(self)
        self.catalog_session_id = ""
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
                "fixture.catalog_status": Locator(
                    LocatorStrategy.ACCESSIBILITY_ID,
                    "catalog-status",
                    "Android API-backed catalog status",
                ),
                "fixture.catalog_archive": Locator(
                    LocatorStrategy.ACCESSIBILITY_ID,
                    "catalog-archive",
                    "Android archive catalog item button",
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
                PlatformCapability.CATALOG,
                PlatformCapability.DIAGNOSTICS,
            }
        )

    @property
    def locators(self) -> LocatorSet:
        return self._locators

    @property
    def files(self) -> AndroidFixtureFilePort:
        return self._files

    @property
    def catalog(self) -> AndroidFixtureCatalogPort:
        return self._catalog

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

    def wait_text_prefix(self, locator_key: str, prefix: str) -> str:
        return self._wait.text_starts_with(
            self._driver,
            self.locators.get(locator_key),
            prefix,
        ).text

    def wait_catalog_snapshot(self, session_id: str) -> CatalogSnapshot:
        deadline = time.monotonic() + self._policy.timeout_seconds
        last_status = ""
        while time.monotonic() < deadline:
            last_status = self.text("fixture.catalog_status")
            if last_status.startswith(
                ("catalog: active|", "catalog: archived|", "catalog: error|")
            ):
                return _snapshot_from_status(last_status, session_id)
            time.sleep(self._policy.poll_interval_seconds)
        raise TimeoutError(
            f"Android catalog status did not settle: {last_status!r}"
        )

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


def _snapshot_from_status(status: str, session_id: str) -> CatalogSnapshot:
    payload = status.removeprefix("catalog: ")
    if payload.startswith("error|"):
        return CatalogSnapshot(
            session_id=session_id,
            item_id=0,
            name=payload.removeprefix("error|") or "unknown",
            status="error",
        )
    parts = payload.split("|", 2)
    if len(parts) != 3:
        raise RuntimeError(f"invalid Android catalog status: {status!r}")
    state, raw_item_id, name = parts
    return CatalogSnapshot(
        session_id=session_id,
        item_id=int(raw_item_id),
        name=name,
        status=state,
    )
