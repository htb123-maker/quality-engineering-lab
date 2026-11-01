"""Unit tests for Xcode-compatible iOS Simulator selection."""

import pytest

from scripts.select_ios_simulator_matrix import SimulatorDevice, select_matrix


def simulator(
    name: str,
    udid: str,
    major: int,
    minor: int,
) -> SimulatorDevice:
    return SimulatorDevice(
        name=name,
        udid=udid,
        version=f"{major}.{minor}",
        major=major,
        minor=minor,
    )


def test_runtime_version_filters_out_newer_incompatible_runtime() -> None:
    devices = (
        simulator("iPhone 16", "ios-18-primary", 18, 5),
        simulator("iPhone 16 Plus", "ios-18-secondary", 18, 5),
        simulator("iPhone 17", "ios-26", 26, 2),
    )

    selected = select_matrix(devices, runtime_version="18.5")

    assert selected["current"]["udid"] == "ios-18-primary"
    assert selected["secondary"]["udid"] == "ios-18-secondary"
    assert "previous" not in selected


def test_missing_explicit_runtime_reports_available_versions() -> None:
    devices = (simulator("iPhone 17", "ios-26", 26, 2),)

    with pytest.raises(ValueError, match="available versions: 26.2"):
        select_matrix(devices, runtime_version="18.5")


def test_previous_major_is_selected_when_available() -> None:
    devices = (
        simulator("iPhone 16", "ios-18-primary", 18, 5),
        simulator("iPhone 16 Plus", "ios-18-secondary", 18, 5),
        simulator("iPhone 15", "ios-17", 17, 5),
    )

    selected = select_matrix(devices, runtime_version="18.5")

    assert selected["previous"]["udid"] == "ios-17"
