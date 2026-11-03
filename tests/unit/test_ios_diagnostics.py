"""Unit tests for iOS screenshot and page-source diagnostics."""

from pathlib import Path
from typing import cast

import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.platforms.ios import IosDiagnostics


class FakeDiagnosticDriver:
    def get_screenshot_as_png(self) -> bytes:
        return b"png-bytes"

    @property
    def page_source(self) -> str:
        return "<AppiumHierarchy />"


def test_ios_diagnostics_writes_screenshot_and_page_source(tmp_path: Path) -> None:
    diagnostics = IosDiagnostics(
        cast(WebDriver, FakeDiagnosticDriver()),
        tmp_path / "evidence",
    )

    capture = diagnostics.capture("02 camera granted")

    assert capture.step == "02-camera-granted"
    assert capture.screenshot_path.read_bytes() == b"png-bytes"
    assert capture.page_source_path.read_text(encoding="utf-8") == "<AppiumHierarchy />"


def test_ios_diagnostics_rejects_empty_step(tmp_path: Path) -> None:
    diagnostics = IosDiagnostics(
        cast(WebDriver, FakeDiagnosticDriver()),
        tmp_path,
    )

    with pytest.raises(ValueError, match="letter or digit"):
        diagnostics.capture("---")
