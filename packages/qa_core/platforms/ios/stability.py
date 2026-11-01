"""JUnit-based iOS stability summaries without retry masking."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class IosTestStatus(StrEnum):
    """Normalized status for one pytest testcase."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    XFAILED = "xfailed"


@dataclass(frozen=True, slots=True)
class IosTestResult:
    """One test result parsed from a pytest JUnit report."""

    node_id: str
    status: IosTestStatus
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class IosRunResult:
    """All testcase results from one pytest invocation."""

    run_index: int
    junit_path: Path
    results: tuple[IosTestResult, ...]


@dataclass(frozen=True, slots=True)
class IosStabilitySummary:
    """Aggregate first-run statuses across repeated iOS executions."""

    runs: int
    required_runs: int
    total_results: int
    passed: int
    failed: int
    skipped: int
    xfailed: int
    pass_rate: float
    flaky_candidates: tuple[str, ...]
    flaky_rate: float
    duration_p50_seconds: float
    duration_p95_seconds: float
    pass_threshold: float
    flaky_threshold: float
    passed_gate: bool

    def to_payload(self) -> dict[str, Any]:
        """Return a deterministic JSON-ready stability report."""

        return {
            "schema_version": 1,
            "runs": self.runs,
            "required_runs": self.required_runs,
            "total_results": self.total_results,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "xfailed": self.xfailed,
            "pass_rate": self.pass_rate,
            "flaky_candidates": list(self.flaky_candidates),
            "flaky_rate": self.flaky_rate,
            "duration_p50_seconds": self.duration_p50_seconds,
            "duration_p95_seconds": self.duration_p95_seconds,
            "pass_threshold": self.pass_threshold,
            "flaky_threshold": self.flaky_threshold,
            "passed_gate": self.passed_gate,
        }


def read_junit_results(path: Path, *, run_index: int) -> IosRunResult:
    """Parse pass, fail, skip, and xfail states from one JUnit XML file."""

    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"invalid pytest JUnit report: {path}") from exc

    results: list[IosTestResult] = []
    for testcase in root.findall(".//testcase"):
        classname = testcase.get("classname", "").strip()
        name = testcase.get("name", "").strip()
        if not name:
            raise ValueError(f"JUnit report {path} contains a testcase without a name")
        node_id = f"{classname}::{name}" if classname else name
        results.append(
            IosTestResult(
                node_id=node_id,
                status=_status(testcase),
                duration_seconds=_duration(testcase.get("time")),
            )
        )
    if not results:
        raise ValueError(f"JUnit report {path} contains no test results")
    return IosRunResult(
        run_index=run_index,
        junit_path=path,
        results=tuple(results),
    )


def summarize_stability(
    runs: Sequence[IosRunResult],
    *,
    required_runs: int,
    pass_threshold: float = 0.98,
    flaky_threshold: float = 0.02,
) -> IosStabilitySummary:
    """Aggregate first-seen outcomes and identify genuinely mixed results."""

    if not runs:
        raise ValueError("at least one iOS stability run is required")
    if required_runs < 1:
        raise ValueError("required_runs must be at least 1")
    if not 0.0 <= pass_threshold <= 1.0:
        raise ValueError("pass_threshold must be between 0 and 1")
    if not 0.0 <= flaky_threshold <= 1.0:
        raise ValueError("flaky_threshold must be between 0 and 1")

    statuses: dict[str, list[IosTestStatus]] = defaultdict(list)
    counts: Counter[IosTestStatus] = Counter()
    durations: list[float] = []
    for run in runs:
        for result in run.results:
            counts[result.status] += 1
            durations.append(result.duration_seconds)
            if result.status in {IosTestStatus.PASSED, IosTestStatus.FAILED}:
                statuses[result.node_id].append(result.status)

    executed = counts[IosTestStatus.PASSED] + counts[IosTestStatus.FAILED]
    pass_rate = counts[IosTestStatus.PASSED] / executed if executed else 0.0
    flaky_candidates = tuple(
        sorted(
            node_id
            for node_id, observed in statuses.items()
            if IosTestStatus.PASSED in observed
            and IosTestStatus.FAILED in observed
        )
    )
    comparable = len(statuses)
    flaky_rate = len(flaky_candidates) / comparable if comparable else 0.0
    passed_gate = (
        len(runs) >= required_runs
        and executed > 0
        and pass_rate >= pass_threshold
        and flaky_rate < flaky_threshold
    )

    return IosStabilitySummary(
        runs=len(runs),
        required_runs=required_runs,
        total_results=sum(counts.values()),
        passed=counts[IosTestStatus.PASSED],
        failed=counts[IosTestStatus.FAILED],
        skipped=counts[IosTestStatus.SKIPPED],
        xfailed=counts[IosTestStatus.XFAILED],
        pass_rate=pass_rate,
        flaky_candidates=flaky_candidates,
        flaky_rate=flaky_rate,
        duration_p50_seconds=_percentile(durations, 50),
        duration_p95_seconds=_percentile(durations, 95),
        pass_threshold=pass_threshold,
        flaky_threshold=flaky_threshold,
        passed_gate=passed_gate,
    )


def _status(testcase: ET.Element) -> IosTestStatus:
    if testcase.find("failure") is not None or testcase.find("error") is not None:
        return IosTestStatus.FAILED
    skipped = testcase.find("skipped")
    if skipped is None:
        return IosTestStatus.PASSED
    skipped_type = (skipped.get("type") or "").casefold()
    message = (skipped.get("message") or "").casefold()
    if "xfail" in skipped_type or "xfail" in message:
        return IosTestStatus.XFAILED
    return IosTestStatus.SKIPPED


def _duration(raw: str | None) -> float:
    try:
        value = float(raw or "0")
    except ValueError as exc:
        raise ValueError(f"invalid JUnit duration: {raw!r}") from exc
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"invalid JUnit duration: {raw!r}")
    return value


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = math.ceil((percentile / 100.0) * len(ordered)) - 1
    return ordered[max(0, min(rank, len(ordered) - 1))]
