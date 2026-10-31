"""Persist iOS screenshots and page source for each meaningful test step."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from appium.webdriver.webdriver import WebDriver

_SAFE_STEP = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class IosDiagnosticsCapture:
    """Files written for one iOS diagnostic step."""

    step: str
    screenshot_path: Path
    page_source_path: Path


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
