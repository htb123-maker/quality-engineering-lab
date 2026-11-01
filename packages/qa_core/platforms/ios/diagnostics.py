"""Persist iOS screenshots and page source for each meaningful test step."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from appium.webdriver.webdriver import WebDriver

_SAFE_STEP = re.compile(r"[^A-Za-z0-9._-]+")
_SECRET_URL = re.compile(r"(https?://)[^/@\s]+:[^/@\s]+@", re.IGNORECASE)
_SECRET_KEY = re.compile(
    r"(access[_-]?key|api[_-]?key|password|private[_-]?key|secret|token)",
    re.IGNORECASE,
)
_REDACTED = "<redacted>"


class IosFailureClass(StrEnum):
    """Evidence-based failure layers used by iOS diagnostics."""

    PRODUCT = "PRODUCT"
    TEST_CODE = "TEST_CODE"
    TEST_DATA = "TEST_DATA"
    DEVICE = "DEVICE"
    ENVIRONMENT = "ENVIRONMENT"
    NETWORK = "NETWORK"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class IosDiagnosticsCapture:
    """Files written for one iOS diagnostic step."""

    step: str
    screenshot_path: Path
    page_source_path: Path


@dataclass(frozen=True, slots=True)
class IosFailureCapture:
    """Files and candidate classification for one failed iOS test."""

    capture: IosDiagnosticsCapture
    manifest_path: Path
    failure_type: IosFailureClass


def classify_ios_failure(error: BaseException) -> IosFailureClass:
    """Classify strong textual signals; ambiguous failures stay UNKNOWN."""

    text = f"{type(error).__name__} {error}".casefold()
    if any(
        marker in text
        for marker in (
            "elementwaittimeout",
            "nosuchelement",
            "staleelement",
            "locator",
        )
    ):
        return IosFailureClass.TEST_CODE
    if any(marker in text for marker in ("invalid test data", "fixture data")):
        return IosFailureClass.TEST_DATA
    if any(
        marker in text
        for marker in (
            "wda",
            "webdriveragent",
            "appium",
            "simulator",
            "xcode",
            "websocket",
            "connection refused",
        )
    ):
        return IosFailureClass.ENVIRONMENT
    if any(marker in text for marker in ("network", "dns", "timed out")):
        return IosFailureClass.NETWORK
    if "assertionerror" in text or "assertion failed" in text:
        return IosFailureClass.PRODUCT
    return IosFailureClass.UNKNOWN


class IosDiagnostics:
    """Capture deterministic image and hierarchy evidence without hiding failures."""

    def __init__(self, driver: WebDriver, directory: Path) -> None:
        self._driver = driver
        self._directory = directory

    def capture(self, step: str) -> IosDiagnosticsCapture:
        """Write one PNG and one page-source file for a named step."""

        normalized = _SAFE_STEP.sub("-", step).strip("-")
        if not normalized:
            raise ValueError("diagnostic step must contain a letter or digit")
        self._directory.mkdir(parents=True, exist_ok=True)
        screenshot_path = self._directory / f"{normalized}.png"
        source_path = self._directory / f"{normalized}.xml"
        screenshot_path.write_bytes(self._driver.get_screenshot_as_png())
        source_path.write_text(self._driver.page_source, encoding="utf-8")
        return IosDiagnosticsCapture(
            step=normalized,
            screenshot_path=screenshot_path,
            page_source_path=source_path,
        )

    def capture_failure(
        self,
        step: str,
        *,
        test_id: str,
        error: BaseException,
        context: dict[str, Any] | None = None,
    ) -> IosFailureCapture:
        """Persist screenshot, hierarchy, and a sanitized failure manifest."""

        if not test_id.strip():
            raise ValueError("failure test_id must not be empty")
        capture = self.capture(step)
        failure_type = classify_ios_failure(error)
        manifest_path = self._directory / f"{capture.step}.failure.json"
        payload: dict[str, Any] = {
            "schema_version": 1,
            "captured_at": datetime.now(UTC).isoformat(),
            "test_id": _redact_text(test_id),
            "failure_type": failure_type.value,
            "error_type": type(error).__name__,
            "error_message": _redact_text(str(error)),
            "screenshot": capture.screenshot_path.name,
            "page_source": capture.page_source_path.name,
            "context": _redact_value(context or {}),
        }
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return IosFailureCapture(
            capture=capture,
            manifest_path=manifest_path,
            failure_type=failure_type,
        )


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                _REDACTED
                if _SECRET_KEY.search(str(key))
                or "udid" in str(key).casefold()
                else _redact_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return _redact_text(str(value))


def _redact_text(value: str) -> str:
    return _SECRET_URL.sub(rf"\1{_REDACTED}@", value)
