"""Unit tests for repeated-run leak comparison."""

import pytest
from qa_core.reporting import (
    EnvironmentSnapshot,
    compare_snapshots,
    parse_pytest_summary,
)


def _snapshot(**overrides: object) -> EnvironmentSnapshot:
    values: dict[str, object] = {
        "captured_at": "2026-10-03T00:00:00+00:00",
        "appium_sessions": (),
        "open_ports": (4723, 18000),
        "processes": {"appium": 2, "adb": 1},
    }
    values.update(overrides)
    return EnvironmentSnapshot.model_validate(values)


def _spawned(**overrides: object) -> EnvironmentSnapshot:
    values: dict[str, object] = {
        "captured_at": "2026-10-03T01:00:00+00:00",
        "appium_sessions": ("abc-123",),
        "open_ports": (4723, 18000, 8200),
        "processes": {"appium": 3, "adb": 1},
    }
    values.update(overrides)
    return _snapshot(**values)


@pytest.mark.unit
def test_stable_environment_is_not_reported_as_a_leak() -> None:
    verdict = compare_snapshots(_snapshot(), _snapshot())

    assert verdict.leaked is False
    assert verdict.port_leak is False
    assert verdict.ports_closed == ()


@pytest.mark.unit
def test_sessions_ports_and_processes_report_each_leak_class() -> None:
    verdict = compare_snapshots(_snapshot(), _spawned())

    assert verdict.leaked is True
    assert verdict.session_leak is True
    assert verdict.new_appium_sessions == ("abc-123",)
    assert verdict.port_leak is True
    assert verdict.ports_opened == (8200,)
    assert verdict.process_leak is True
    assert verdict.process_growth == {"appium": 1}


@pytest.mark.unit
def test_closed_baseline_port_is_diagnostic_not_a_leak() -> None:
    verdict = compare_snapshots(_snapshot(), _snapshot(open_ports=(18000,)))

    assert verdict.leaked is False
    assert verdict.ports_closed == (4723,)


@pytest.mark.unit
def test_pytest_summary_returns_last_outcome_line() -> None:
    output = "collected 1 item\n\n.  [100%]\n1 passed in 0.20s\n"

    assert parse_pytest_summary(output) == "1 passed in 0.20s"
    assert parse_pytest_summary("no summary here") == ""
