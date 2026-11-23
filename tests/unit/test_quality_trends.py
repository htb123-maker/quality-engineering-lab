"""Week 31 quality trend and governance contracts."""

from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from qa_core.reporting import (
    REQUIRED_PIPELINE_CHECKS,
    JUnitCounts,
    TrendHistory,
    append_history,
    build_trend_point,
    discover_checks,
    load_quality_governance,
    missing_required_checks,
    parse_junit,
    render_trend_html,
    with_required_check_placeholders,
)


def test_parse_junit_aggregates_nested_suites(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(
        """
<testsuites>
  <testsuite tests="2" failures="1" errors="0" skipped="0" time="1.2"/>
  <testsuite tests="3" failures="0" errors="1" skipped="1" time="2.3"/>
</testsuites>
""",
        encoding="utf-8",
    )

    counts = parse_junit(path)

    assert counts == JUnitCounts(
        tests=5,
        failures=1,
        errors=1,
        skipped=1,
        duration_seconds=3.5,
    )


def test_discover_checks_reads_junit_and_status_json(tmp_path: Path) -> None:
    (tmp_path / "android").mkdir()
    (tmp_path / "android" / "android-junit.xml").write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="0" time="0.2"/>',
        encoding="utf-8",
    )
    (tmp_path / "ios").mkdir()
    (tmp_path / "ios" / "weak-network.json").write_text(
        '{"status":"PASS"}',
        encoding="utf-8",
    )
    (tmp_path / "performance").mkdir()
    (tmp_path / "performance" / "result.json").write_text(
        '{"slo_passed":true}',
        encoding="utf-8",
    )
    (tmp_path / "performance" / "warmup").mkdir()
    (tmp_path / "performance" / "warmup" / "result.json").write_text(
        '{"slo_passed":true}',
        encoding="utf-8",
    )

    checks = discover_checks(tmp_path)

    assert [check.outcome for check in checks] == ["PASS", "PASS", "PASS"]
    assert checks[-1].name == "json:performance/result"
    assert [check.name for check in checks].count("json:performance/result") == 1


def test_performance_slo_failure_is_failed(tmp_path: Path) -> None:
    path = tmp_path / "performance" / "result.json"
    path.parent.mkdir()
    path.write_text('{"slo_passed":false}', encoding="utf-8")

    checks = discover_checks(tmp_path)

    assert [(check.name, check.outcome) for check in checks] == [
        ("json:performance/result", "FAILED")
    ]


def test_append_history_replaces_same_run_and_is_bounded() -> None:
    first = build_trend_point(run_id="1", commit="a", checks=())
    second = build_trend_point(run_id="2", commit="b", checks=())
    replacement = build_trend_point(run_id="1", commit="c", checks=())

    history = append_history(TrendHistory(points=(first, second)), replacement)
    bounded = append_history(history, replacement, max_points=1)

    assert [point.run_id for point in history.points] == ["2", "1"]
    assert history.points[-1].commit == "c"
    assert len(bounded.points) == 1
    assert "Quality Trend" in render_trend_html(history)


def test_required_pipeline_checks_turn_missing_evidence_into_not_run() -> None:
    observed = build_trend_point(run_id="1", commit="a", checks=()).checks

    missing = missing_required_checks(observed, REQUIRED_PIPELINE_CHECKS)
    completed = with_required_check_placeholders(
        observed,
        REQUIRED_PIPELINE_CHECKS,
    )

    assert len(missing) == len(REQUIRED_PIPELINE_CHECKS)
    assert {check.outcome for check in completed} == {"NOT RUN"}
    assert {check.name for check in completed} == set(REQUIRED_PIPELINE_CHECKS)


def test_governance_rejects_expired_quarantine(tmp_path: Path) -> None:
    path = tmp_path / "governance.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "owners": {
                    "quality": "quality",
                    "api": "api",
                    "android": "android",
                    "ios": "ios",
                    "performance": "performance",
                    "infrastructure": "infra",
                },
                "quarantine": [
                    {
                        "node_id": "tests/ios/test_example.py::test_flaky",
                        "owner": "ios",
                        "reason": "provider instability",
                        "expires_on": (date.today() - timedelta(days=1)).isoformat(),
                        "evidence": "run-1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expired quarantine"):
        load_quality_governance(path, today=date.today())
