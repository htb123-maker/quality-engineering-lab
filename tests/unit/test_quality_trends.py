"""Week 31 quality trend and governance contracts."""

from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from qa_core.reporting import (
    JUnitCounts,
    TrendHistory,
    append_history,
    build_trend_point,
    discover_checks,
    load_quality_governance,
    parse_junit,
    render_trend_html,
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

    checks = discover_checks(tmp_path)

    assert [check.outcome for check in checks] == ["PASS", "PASS"]


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
