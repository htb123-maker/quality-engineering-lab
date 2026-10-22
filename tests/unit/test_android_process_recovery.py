"""Unit tests for the Android process-recovery acceptance script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
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
