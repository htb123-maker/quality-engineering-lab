"""Unit tests for same-device multi-session port isolation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from qa_core.config.settings import Settings


def _load_same_device_ports() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "verify_android_same_device_ports.py"
    )
    spec = importlib.util.spec_from_file_location(
        "week16_android_same_device_ports",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_same_device_settings_use_distinct_service_ports() -> None:
    module = _load_same_device_ports()
    base = Settings(_env_file=None)

    first = module.build_settings(
        base,
        label="same-device-primary",
        server_url="http://127.0.0.1:4723",
        serial="emulator-5554",
        system_port=8200,
        mjpeg_server_port=7810,
        package="com.example.qaweek15",
        activity=".MainActivity",
    )
    second = module.build_settings(
        base,
        label="same-device-secondary",
        server_url="http://127.0.0.1:4724",
        serial="emulator-5554",
        system_port=8201,
        mjpeg_server_port=7811,
        package="com.example.qaweek15",
        activity=".MainActivity",
    )

    assert first.android_udid == second.android_udid == "emulator-5554"
    assert first.android_system_port == 8200
    assert second.android_system_port == 8201
    assert first.android_mjpeg_server_port == 7810
    assert second.android_mjpeg_server_port == 7811
