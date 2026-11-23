"""Tests for real CI artifact ingestion into monitoring agents."""

from __future__ import annotations

import json
from pathlib import Path

from ai.agents.artifact_monitor import build_monitoring_report


def _junit(path: Path, *, failures: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            f'<testsuite tests="1" failures="{failures}" errors="0" '
            'skipped="0" time="0.1"/>'
        ),
        encoding="utf-8",
    )


def _json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _complete_artifacts(root: Path) -> None:
    for name in (
        "quality-junit.xml",
        "sut-junit.xml",
        "api-junit.xml",
        "android-junit.xml",
        "android-business-junit.xml",
        "ios-simulator-junit.xml",
    ):
        _junit(root / "collected" / name)
    _json(root / "collected" / "smoke" / "result.json", {"slo_passed": True})
    _json(root / "collected" / "agent-eval.json", {"status": "PASS"})


def test_monitor_maps_real_artifacts_to_ci_and_performance_agents(
    tmp_path: Path,
) -> None:
    _complete_artifacts(tmp_path)

    report = build_monitoring_report(
        tmp_path / "collected",
        run_id="42",
        commit="abc123",
    )

    assert report["status"] == "PASS"
    assert report["run_id"] == "42"
    assert report["commit"] == "abc123"
    assert report["missing_signals"] == []
    assert {agent["id"] for agent in report["agents"]} == {
        "ci-monitor",
        "performance-monitor",
    }
    assert all(agent["outcome"] == "PASS" for agent in report["agents"])
    assert report["automatic_writes"] == 0


def test_monitor_fails_closed_when_performance_is_missing(tmp_path: Path) -> None:
    _complete_artifacts(tmp_path)
    (tmp_path / "collected" / "smoke" / "result.json").unlink()

    report = build_monitoring_report(
        tmp_path / "collected",
        run_id="42",
        commit="abc123",
    )

    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["missing_signals"] == ["performance"]
    performance = next(
        agent for agent in report["agents"] if agent["id"] == "performance-monitor"
    )
    assert performance["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert performance["requires_human_approval"] is True


def test_monitor_preserves_failed_junit_evidence(tmp_path: Path) -> None:
    _complete_artifacts(tmp_path)
    _junit(tmp_path / "collected" / "api-junit.xml", failures=1)

    report = build_monitoring_report(
        tmp_path / "collected",
        run_id="42",
        commit="abc123",
    )

    assert report["status"] == "FAILED"
    ci = next(agent for agent in report["agents"] if agent["id"] == "ci-monitor")
    assert ci["outcome"] == "FAILED"
    assert ci["suspected_layer"] == "api"
