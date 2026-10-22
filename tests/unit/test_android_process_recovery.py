"""Unit tests for the Android process-recovery acceptance script."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings


def _load_process_recovery() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "verify_android_process_recovery.py"
    )
    spec = importlib.util.spec_from_file_location(
        "week16_android_process_recovery",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_parse_launch_state_reads_cold_and_hot() -> None:
    module = _load_process_recovery()

    assert module.parse_launch_state("Status: ok\nLaunchState: COLD\n") == "COLD"
    assert module.parse_launch_state("LaunchState: HOT\n") == "HOT"
    assert module.parse_launch_state("Status: ok\n") == "unknown"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("activity", "expected"),
    [
        (".MainActivity", "com.example.qaweek15.MainActivity"),
        ("com.example.qaweek15.MainActivity", "com.example.qaweek15.MainActivity"),
    ],
)
def test_normalized_component_activity(activity: str, expected: str) -> None:
    module = _load_process_recovery()

    assert module.normalized_component_activity("com.example.qaweek15", activity) == expected


@pytest.mark.unit
def test_process_recovery_settings_target_explicit_device() -> None:
    module = _load_process_recovery()

    settings = module.build_settings(
        Settings(_env_file=None),
        serial="172.20.10.10:37699",
        package="com.example.qaweek15",
        activity=".MainActivity",
    )

    assert settings.android_udid == "172.20.10.10:37699"
    assert settings.android_device_name == "process-recovery"
    assert settings.android_app_package == "com.example.qaweek15"
    assert settings.android_app_activity == ".MainActivity"


@pytest.mark.unit
def test_soft_kill_sends_home_before_am_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_process_recovery()
    keycodes: list[int] = []
    commands: list[tuple[str, ...]] = []

    class FakeDriver:
        def press_keycode(self, keycode: int) -> None:
            keycodes.append(keycode)

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    def fake_run_adb(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return completed

    monkeypatch.setattr(module, "run_adb", fake_run_adb)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    module.stop_package(
        "adb.exe",
        "172.20.10.10:37699",
        "com.example.qaweek15",
        "am-kill",
        cast(WebDriver, FakeDriver()),
    )

    assert keycodes == [3]
    assert commands == [
        (
            "adb.exe",
            "172.20.10.10:37699",
            "shell",
            "am",
            "kill",
            "com.example.qaweek15",
        )
    ]
