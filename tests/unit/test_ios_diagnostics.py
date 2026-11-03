"""Unit tests for iOS screenshot and page-source diagnostics."""

import json
from pathlib import Path
from typing import cast

import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.platforms.ios import (
    IosDiagnostics,
    IosFailureClass,
    classify_ios_failure,
)


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


def test_failure_manifest_redacts_credentials_and_udid(tmp_path: Path) -> None:
    diagnostics = IosDiagnostics(
        cast(WebDriver, FakeDiagnosticDriver()),
        tmp_path,
    )
    error = AssertionError(
        "request failed at https://user:password@example.test/session"
    )

    failure = diagnostics.capture_failure(
        "01 failed assertion",
        test_id="IOS-EXAMPLE-001",
        error=error,
        context={
            "access_key": "do-not-store",
            "udid": "device-secret",
            "provider": "browserstack",
        },
    )

    payload = json.loads(failure.manifest_path.read_text(encoding="utf-8"))
    assert failure.failure_type is IosFailureClass.PRODUCT
    assert payload["context"]["access_key"] == "<redacted>"
    assert payload["context"]["udid"] == "<redacted>"
    assert payload["context"]["provider"] == "browserstack"
    assert "do-not-store" not in json.dumps(payload)
    assert "device-secret" not in json.dumps(payload)
    assert "user:password" not in payload["error_message"]


def test_failure_classifier_keeps_ambiguous_errors_unknown() -> None:
    assert classify_ios_failure(RuntimeError("WebDriverAgent launch failed")) is (
        IosFailureClass.ENVIRONMENT
    )
    assert classify_ios_failure(RuntimeError("unexpected edge case")) is (
        IosFailureClass.UNKNOWN
    )
