"""Android capabilities stay explicit and platform-specific."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import appium.webdriver
import pytest
from qa_core.config.settings import Settings
from qa_core.driver.android import build_android_options, create_android_driver


@pytest.mark.unit
def test_android_options_map_typed_settings_to_uiautomator2_capabilities() -> None:
    settings = Settings(
        android_udid="emulator-5556",
        android_device_name="Pixel_API_35_Test",
        android_platform_version="15",
        android_app_package="com.example.demo",
        android_app_activity=".MainActivity",
        android_adb_exec_timeout_ms=75_000,
    )

    capabilities = build_android_options(settings).to_capabilities()

    assert capabilities["platformName"] == "Android"
    assert capabilities["appium:automationName"] == "UiAutomator2"
    assert capabilities["appium:udid"] == "emulator-5556"
    assert capabilities["appium:deviceName"] == "Pixel_API_35_Test"
    assert capabilities["appium:platformVersion"] == "15"
    assert capabilities["appium:appPackage"] == "com.example.demo"
    assert capabilities["appium:appActivity"] == ".MainActivity"
    assert capabilities["appium:adbExecTimeout"] == 75_000
    assert capabilities["appium:noReset"] is True
    assert capabilities["appium:newCommandTimeout"] == 300


@pytest.mark.unit
def test_android_driver_uses_the_configured_appium_endpoint_without_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_remote(
        *,
        command_executor: str,
        options: Mapping[str, Any],
    ) -> object:
        captured["command_executor"] = command_executor
        captured["options"] = options
        return sentinel

    monkeypatch.setattr(appium.webdriver, "Remote", fake_remote)
    settings = Settings(appium_server_url="http://127.0.0.1:4723")

    driver = create_android_driver(settings)

    assert driver is sentinel
    assert captured["command_executor"] == "http://127.0.0.1:4723"
    assert captured["options"].to_capabilities()["appium:udid"] == "emulator-5554"
