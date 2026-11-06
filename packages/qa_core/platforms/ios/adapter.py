"""iOS implementation of the shared fixture adapter contract."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping
from pathlib import Path

from appium.webdriver.webdriver import WebDriver

from qa_core.mobile.diagnostics import MobileDiagnostics, MobileFailureEvidence
from qa_core.mobile.platforms import (
    CatalogSnapshot,
    LocatorSet,
    MobilePlatform,
    NavigationOutcome,
    PlatformCapability,
)
from qa_core.mobile.waits import MobileWait, WaitPolicy
from qa_core.platforms.ios.locators import IosLocator


class IosFixtureFilePort:
    """iOS fixture UI implementation of the shared file port."""

    SUPPORTED_CONTENT = "week19-file"

    def __init__(self, adapter: IosFixtureAdapter) -> None:
        self._adapter = adapter

    def write_text(self, content: str) -> None:
        if content != self.SUPPORTED_CONTENT:
            raise ValueError(
                "iOS fixture supports only the stable content "
                f"{self.SUPPORTED_CONTENT!r}"
            )
        self._adapter.tap("fixture.write_file_button")
        self._adapter.wait_text("fixture.file_status", "file: written")

    def read_text(self) -> str:
        self._adapter.tap("fixture.read_file_button")
        status = self._adapter.wait_text_prefix(
            "fixture.file_status",
            "file: read ",
        )
        return status.removeprefix("file: read ")

    def cleanup(self) -> None:
        self._adapter.tap("fixture.delete_file_button")
        self._adapter.wait_text("fixture.file_status", "file: deleted")


class IosFixtureCatalogPort:
    """API-backed catalog operations implemented by the iOS fixture."""

    def __init__(self, adapter: IosFixtureAdapter) -> None:
        self._adapter = adapter

    def open(self, *, base_url: str, session_id: str) -> CatalogSnapshot:
        payload = base64.urlsafe_b64encode(
            json.dumps(
                {"e2eBaseUrl": base_url, "sessionId": session_id},
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).decode("ascii").rstrip("=")
        url = f"qaweek19://e2e/{payload}"
        self._adapter._driver.execute_script(  # noqa: SLF001
            "mobile: deepLink",
            {"url": url, "bundleId": self._adapter._bundle_id},  # noqa: SLF001
        )
        self._adapter.catalog_session_id = session_id
        return self._adapter.wait_catalog_snapshot(session_id)

    def archive(self) -> CatalogSnapshot:
        self._adapter.tap("fixture.catalog_archive")
        return self._adapter.wait_catalog_snapshot(self._adapter.catalog_session_id)


class IosFixtureAdapter:
    """Cross-platform fixture operations backed by XCUITest."""

    NAVIGATION_URL = "qaweek19://system-interactions?case=deep-link"

    def __init__(
        self,
        driver: WebDriver,
        *,
        bundle_id: str,
        wait_policy: WaitPolicy | None = None,
        diagnostics_directory: Path | None = None,
    ) -> None:
        if not bundle_id.strip():
            raise ValueError("bundle_id must not be empty")
        self._driver = driver
        self._bundle_id = bundle_id
        self._policy = wait_policy or WaitPolicy()
        self._wait = MobileWait(driver, self._policy)
        self._files = IosFixtureFilePort(self)
        self._catalog = IosFixtureCatalogPort(self)
        self.catalog_session_id = ""
        self._diagnostics = (
            MobileDiagnostics(driver, diagnostics_directory)
            if diagnostics_directory is not None
            else None
        )
        self._locators = LocatorSet(
            MobilePlatform.IOS,
            {
                "fixture.root": IosLocator.class_chain(
                    "**/XCUIElementTypeWindow[1]",
                    "iOS fixture root",
                ),
                "fixture.title": IosLocator.accessibility_id(
                    "fixture-title",
                    "iOS fixture title",
                ),
                "fixture.navigation_button": IosLocator.accessibility_id(
                    "simulate-deep-link",
                    "iOS fixture navigation button",
                ),
                "fixture.navigation_status": IosLocator.accessibility_id(
                    "deep-link-status",
                    "iOS fixture navigation status",
                ),
                "fixture.write_file_button": IosLocator.accessibility_id(
                    "write-file",
                    "iOS write file button",
                ),
                "fixture.read_file_button": IosLocator.accessibility_id(
                    "read-file",
                    "iOS read file button",
                ),
                "fixture.delete_file_button": IosLocator.accessibility_id(
                    "delete-file",
                    "iOS delete file button",
                ),
                "fixture.file_status": IosLocator.accessibility_id(
                    "file-status",
                    "iOS file status",
                ),
                "fixture.catalog_status": IosLocator.accessibility_id(
                    "catalog-status",
                    "iOS API-backed catalog status",
                ),
                "fixture.catalog_archive": IosLocator.accessibility_id(
                    "catalog-archive",
                    "iOS archive catalog item button",
                ),
            },
        )

    @property
    def platform(self) -> MobilePlatform:
        return MobilePlatform.IOS

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
    def files(self) -> IosFixtureFilePort:
        return self._files

    @property
    def catalog(self) -> IosFixtureCatalogPort:
        return self._catalog

    def launch_fixture(self) -> None:
        self._driver.terminate_app(self._bundle_id)
        self._driver.activate_app(self._bundle_id)
        self._wait.visible(self._driver, self.locators.get("fixture.root"))
        self._wait.text_is(
            self._driver,
            self.locators.get("fixture.title"),
            "QA iOS Fixture",
        )

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

    def wait_text(self, locator_key: str, expected: str) -> str:
        return self._wait.text_is(
            self._driver,
            self.locators.get(locator_key),
            expected,
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
        raise TimeoutError(f"iOS catalog status did not settle: {last_status!r}")

    def trigger_navigation(self) -> NavigationOutcome:
        self.tap("fixture.navigation_button")
        self.wait_text(
            "fixture.navigation_status",
            f"deep link: opened {self.NAVIGATION_URL}",
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
            "bundle_id": self._bundle_id,
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
        raise RuntimeError(f"invalid iOS catalog status: {status!r}")
    state, raw_item_id, name = parts
    return CatalogSnapshot(
        session_id=session_id,
        item_id=int(raw_item_id),
        name=name,
        status=state,
    )
