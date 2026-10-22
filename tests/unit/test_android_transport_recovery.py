"""Unit tests for the wireless ADB transport-recovery probe."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_transport_recovery() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "verify_android_transport_recovery.py"
    )
    spec = importlib.util.spec_from_file_location(
        "week16_android_transport_recovery",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_wait_for_adb_state_retries_until_device_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_transport_recovery()
    responses = iter(
        [
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="offline"),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="device\n", stderr=""),
        ]
    )

    monkeypatch.setattr(module, "run_adb", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    assert module.wait_for_adb_state("adb.exe", "172.20.10.10:37699", "device") == "device"


@pytest.mark.unit
def test_wait_for_adb_state_returns_last_observation_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_transport_recovery()
    response = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="offline\n",
        stderr="",
    )
    monkeypatch.setattr(module, "run_adb", lambda *args, **kwargs: response)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(module.time, "monotonic", iter([0.0, 0.0, 2.0]).__next__)

    assert (
        module.wait_for_adb_state(
            "adb.exe",
            "172.20.10.10:37699",
            "device",
            timeout_seconds=1,
        )
        == "offline"
    )
