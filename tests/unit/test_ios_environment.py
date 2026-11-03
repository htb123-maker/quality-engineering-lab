"""Unit tests for the Week 17 iOS environment preflight."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_check_ios_environment() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_ios_environment.py"
    )
    spec = importlib.util.spec_from_file_location(
        "week17_check_ios_environment",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def simulator_inventory() -> dict[str, object]:
    return {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-17-5": [
                {
                    "name": "iPhone 15",
                    "udid": "OLD-UDID",
                    "state": "Shutdown",
                    "isAvailable": True,
                },
                {
                    "name": "iPhone 16",
                    "udid": "UNAVAILABLE-UDID",
                    "state": "Shutdown",
                    "isAvailable": False,
                },
            ],
            "com.apple.CoreSimulator.SimRuntime.iOS-18-5": [
                {
                    "name": "iPhone 16",
                    "udid": "NEW-UDID",
                    "state": "Booted",
                    "isAvailable": True,
                }
            ],
            "com.apple.CoreSimulator.SimRuntime.watchOS-11-5": [
                {
                    "name": "Apple Watch",
                    "udid": "WATCH-UDID",
                    "state": "Shutdown",
                    "isAvailable": True,
                }
            ],
        }
    }


@pytest.mark.unit
def test_runtime_version_parses_ios_identifier() -> None:
    module = _load_check_ios_environment()

    assert (
        module.runtime_version("com.apple.CoreSimulator.SimRuntime.iOS-18-5")
        == "18.5"
    )
    assert module.runtime_version("com.apple.CoreSimulator.SimRuntime.iOS-26") == "26"
    assert module.runtime_version("not-an-ios-runtime") == "unknown"


@pytest.mark.unit
def test_select_simulator_prefers_newest_available_ios_runtime() -> None:
    module = _load_check_ios_environment()

    selected = module.select_simulator(
        simulator_inventory(),
        device_name="iPhone 16",
        platform_version=None,
        udid=None,
    )

    assert selected is not None
    assert selected.name == "iPhone 16"
    assert selected.udid == "NEW-UDID"
    assert selected.runtime_version == "18.5"
    assert selected.state == "Booted"


@pytest.mark.unit
def test_select_simulator_honors_udid_and_platform_constraint() -> None:
    module = _load_check_ios_environment()

    selected = module.select_simulator(
        simulator_inventory(),
        device_name="Ignored when a UDID is set",
        platform_version="17.5",
        udid="OLD-UDID",
    )

    assert selected is not None
    assert selected.name == "iPhone 15"
    assert selected.runtime_version == "17.5"


@pytest.mark.unit
def test_select_simulator_ignores_unavailable_and_non_ios_devices() -> None:
    module = _load_check_ios_environment()

    assert (
        module.select_simulator(
            simulator_inventory(),
            device_name="Apple Watch",
            platform_version=None,
            udid=None,
        )
        is None
    )
    assert (
        module.select_simulator(
            simulator_inventory(),
            device_name="iPhone 16",
            platform_version=None,
            udid="UNAVAILABLE-UDID",
        )
        is None
    )


@pytest.mark.unit
def test_xcuitest_driver_reports_installed_version(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_check_ios_environment()
    completed = subprocess.CompletedProcess(
        args=["appium"],
        returncode=0,
        stdout=json.dumps(
            {
                "xcuitest": {
                    "installed": True,
                    "version": "8.4.3",
                }
            }
        ),
        stderr="",
    )
    monkeypatch.setattr(module, "_run_process", lambda command, timeout: (completed, None))

    check = module.check_xcuitest_driver()

    assert check.passed is True
    assert check.detail == "xcuitest@8.4.3"


@pytest.mark.unit
def test_xcuitest_driver_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_check_ios_environment()
    completed = subprocess.CompletedProcess(
        args=["appium"],
        returncode=0,
        stdout="not-json",
        stderr="",
    )
    monkeypatch.setattr(module, "_run_process", lambda command, timeout: (completed, None))

    check = module.check_xcuitest_driver()

    assert check.passed is False
    assert check.detail == "Appium returned invalid JSON"
    assert "Reinstall" in check.remediation


@pytest.mark.unit
@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("  1) HASH \"Apple Development: Dev\"\n     1 valid identities found", 1),
        ("     0 valid identities found", 0),
        ("security: SecKeychainSearchCopyNext: The specified item could not be found.", None),
    ],
)
def test_parse_codesigning_identities(output: str, expected: int | None) -> None:
    module = _load_check_ios_environment()

    assert module.parse_codesigning_identities(output) == expected


@pytest.mark.unit
def test_parse_physical_devices_ignores_macs_and_simulators() -> None:
    module = _load_check_ios_environment()
    output = """
== Devices ==
Developer MacBook Pro (15.5) (MAC-UDID)
QA iPhone (18.0) (IPHONE-UDID)
QA iPad (18.0) (IPAD-UDID)
== Simulators ==
iPhone 16 Simulator (18.5) (SIMULATOR-UDID)
"""

    assert module.parse_physical_devices(output) == ["QA iPhone", "QA iPad"]


@pytest.mark.unit
def test_physical_device_check_fails_without_connected_ios_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_check_ios_environment()
    completed = subprocess.CompletedProcess(
        args=["xcrun"],
        returncode=0,
        stdout="== Devices ==\nDeveloper MacBook Pro (15.5) (MAC-UDID)\n",
        stderr="",
    )
    monkeypatch.setattr(module, "_run_process", lambda command, timeout: (completed, None))

    check = module.check_physical_device()

    assert check.passed is False
    assert "no physical iPhone or iPad" in check.detail
    assert "trust this Mac" in check.remediation


@pytest.mark.unit
def test_main_writes_machine_readable_environment_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_check_ios_environment()
    check = module.CheckResult(name="macOS", passed=True, detail="platform=Darwin")
    monkeypatch.setattr(module, "collect_checks", lambda **kwargs: [check])
    output_path = tmp_path / "ios-environment.json"

    exit_code = module.main(
        [
            "--profile",
            "simulator",
            "--json",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["profile"] == "simulator"
    assert payload["checks"][0]["name"] == "macOS"
