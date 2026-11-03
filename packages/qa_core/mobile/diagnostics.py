"""Platform-neutral failure evidence for shared mobile scenarios."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from appium.webdriver.webdriver import WebDriver

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_SECRET_KEY = re.compile(
    r"(access[_-]?key|api[_-]?key|password|private[_-]?key|secret|token)",
    re.IGNORECASE,
)
_REDACTED = "<redacted>"


@dataclass(frozen=True, slots=True)
class MobileFailureEvidence:
    """Files written for one failed cross-platform scenario step."""

    screenshot_path: Path
    page_source_path: Path
    manifest_path: Path


class MobileDiagnostics:
    """Capture screenshot, page source, and a sanitized scenario manifest."""

    def __init__(self, driver: WebDriver, directory: Path) -> None:
        self._driver = driver
        self._directory = directory

    def capture_failure(
        self,
        *,
        scenario_id: str,
        step_id: str,
        error: BaseException,
        context: Mapping[str, object] | None = None,
    ) -> MobileFailureEvidence:
        """Persist evidence without changing the caller's failure outcome."""

        prefix = _safe_name(f"{scenario_id}-{step_id}")
        self._directory.mkdir(parents=True, exist_ok=True)
        screenshot_path = self._directory / f"{prefix}.png"
        source_path = self._directory / f"{prefix}.xml"
        manifest_path = self._directory / f"{prefix}.failure.json"
        screenshot_path.write_bytes(self._driver.get_screenshot_as_png())
        source_path.write_text(self._driver.page_source, encoding="utf-8")
        payload: dict[str, Any] = {
            "schema_version": 1,
            "captured_at": datetime.now(UTC).isoformat(),
            "scenario_id": scenario_id,
            "step_id": step_id,
            "error_type": type(error).__name__,
            "error_message": _redact(str(error)),
            "screenshot": screenshot_path.name,
            "page_source": source_path.name,
            "context": _redact_value(context or {}),
        }
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return MobileFailureEvidence(
            screenshot_path=screenshot_path,
            page_source_path=source_path,
            manifest_path=manifest_path,
        )


def _safe_name(value: str) -> str:
    normalized = _SAFE_NAME.sub("-", value).strip("-")
    if not normalized:
        raise ValueError("diagnostic name must contain a letter or digit")
    return normalized


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                _REDACTED
                if _SECRET_KEY.search(str(key)) or "udid" in str(key).casefold()
                else _redact_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return _redact(str(value))


def _redact(value: str) -> str:
    return _SECRET_KEY.sub(_REDACTED, value)
