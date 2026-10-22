"""Unit tests for the Android multi-instance acceptance probe."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from qa_core.config.settings import Settings


def _load_multi_instance() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "verify_android_multi_instance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "week16_android_multi_instance",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_multi_instance_settings_bind_one_endpoint_and_serial() -> None:
    module = _load_multi_instance()

    settings = module.build_settings(
        Settings(_env_file=None),
        label="avd-secondary",
        server_url="http://127.0.0.1:4724",
        serial="emulator-5554",
        package="com.example.qaweek15",
        activity=".MainActivity",
    )

    assert str(settings.appium_server_url).startswith("http://127.0.0.1:4724")
    assert settings.android_udid == "emulator-5554"
    assert settings.android_device_name == "avd-secondary"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Counter: 1", "1"),
        ("计数器：2", "2"),
        ("العداد: 3", "3"),
        ("no counter value", ""),
    ],
)
def test_counter_value_is_language_independent(text: str, expected: str) -> None:
    module = _load_multi_instance()

    assert module.counter_value(text) == expected
