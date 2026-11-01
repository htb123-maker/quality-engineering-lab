"""Unit tests for iOS repeated-run stability summaries."""

from pathlib import Path

import pytest
from qa_core.platforms.ios.stability import (
    IosTestStatus,
    read_junit_results,
    summarize_stability,
)


def test_junit_reader_distinguishes_xfail_skip_and_failure(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="ios">
    <testcase classname="tests.ios.test_example" name="test_pass" time="1.5"/>
    <testcase classname="tests.ios.test_example" name="test_fail" time="2.5">
      <failure message="assertion failed"/>
    </testcase>
    <testcase classname="tests.ios.test_example" name="test_xfail" time="0.5">
      <skipped type="pytest.xfail" message="known provider limitation"/>
    </testcase>
    <testcase classname="tests.ios.test_example" name="test_skip" time="0.1">
      <skipped type="pytest.skip" message="not on this host"/>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    run = read_junit_results(path, run_index=1)

    assert [result.status for result in run.results] == [
        IosTestStatus.PASSED,
        IosTestStatus.FAILED,
        IosTestStatus.XFAILED,
        IosTestStatus.SKIPPED,
    ]


def test_stability_summary_keeps_first_outcomes_and_flags_mixed_test(
    tmp_path: Path,
) -> None:
    first = _write_junit(
        tmp_path / "run-1.xml",
        [
            ("test_stable", None),
            ("test_mixed", None),
            ("test_known", "xfail"),
        ],
    )
    second = _write_junit(
        tmp_path / "run-2.xml",
        [
            ("test_stable", None),
            ("test_mixed", "failure"),
            ("test_known", "xfail"),
        ],
    )

    summary = summarize_stability(
        [
            read_junit_results(first, run_index=1),
            read_junit_results(second, run_index=2),
        ],
        required_runs=2,
    )

    assert summary.passed == 3
    assert summary.failed == 1
    assert summary.xfailed == 2
    assert summary.pass_rate == pytest.approx(0.75)
    assert summary.flaky_candidates == ("tests.ios.test_example::test_mixed",)
    assert summary.flaky_rate == pytest.approx(0.5)
    assert summary.passed_gate is False


def test_skips_do_not_count_as_pass_and_required_runs_are_enforced(
    tmp_path: Path,
) -> None:
    path = _write_junit(
        tmp_path / "run.xml",
        [("test_pass", None), ("test_skip", "skip")],
    )
    summary = summarize_stability(
        [read_junit_results(path, run_index=1)],
        required_runs=2,
    )

    assert summary.passed == 1
    assert summary.skipped == 1
    assert summary.pass_rate == pytest.approx(1.0)
    assert summary.passed_gate is False


def _write_junit(
    path: Path,
    cases: list[tuple[str, str | None]],
) -> Path:
    body: list[str] = []
    for name, outcome in cases:
        if outcome == "failure":
            body.append(
                f'<testcase classname="tests.ios.test_example" name="{name}" '
                'time="1.0"><failure message="assertion failed"/></testcase>'
            )
        elif outcome == "xfail":
            body.append(
                f'<testcase classname="tests.ios.test_example" name="{name}" '
                'time="0.5"><skipped type="pytest.xfail"/></testcase>'
            )
        elif outcome == "skip":
            body.append(
                f'<testcase classname="tests.ios.test_example" name="{name}" '
                'time="0.1"><skipped type="pytest.skip"/></testcase>'
            )
        else:
            body.append(
                f'<testcase classname="tests.ios.test_example" name="{name}" '
                'time="1.5"/>'
            )
    path.write_text(
        '<testsuites><testsuite name="ios">'
        + "".join(body)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path
