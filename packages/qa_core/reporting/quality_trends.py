"""Aggregate quality artifacts into a compact historical trend record."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TrendOutcome = Literal[
    "PASS",
    "PARTIAL",
    "FAILED",
    "NOT RUN",
    "BLOCKED",
    "DEFERRED",
]


class JUnitCounts(BaseModel):
    """One JUnit suite's aggregate counts."""

    model_config = ConfigDict(frozen=True)

    tests: int = Field(ge=0)
    failures: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    duration_seconds: float = Field(ge=0.0)


class TrendCheck(BaseModel):
    """One deterministic quality signal for a CI run."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    outcome: TrendOutcome
    evidence: str = Field(min_length=1)
    counts: JUnitCounts | None = None


class TrendPoint(BaseModel):
    """All quality signals collected for one commit and CI run."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    commit: str = Field(min_length=1)
    generated_at: datetime
    checks: tuple[TrendCheck, ...]

    @property
    def overall(self) -> TrendOutcome:
        outcomes = {check.outcome for check in self.checks}
        if "FAILED" in outcomes:
            return "FAILED"
        if outcomes.intersection({"NOT RUN", "BLOCKED"}):
            return "BLOCKED"
        if "PARTIAL" in outcomes or "DEFERRED" in outcomes:
            return "PARTIAL"
        return "PASS" if outcomes else "NOT RUN"


class TrendHistory(BaseModel):
    """Persisted trend points ordered oldest to newest."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    points: tuple[TrendPoint, ...] = ()


def parse_junit(path: Path) -> JUnitCounts:
    """Parse a single ``testsuite`` or nested ``testsuites`` document."""

    root = ElementTree.parse(path).getroot()
    if root.tag == "testsuite":
        suites = [root]
    else:
        suites = list(root.findall(".//testsuite"))
    if not suites:
        raise ValueError(f"JUnit document contains no testsuite: {path}")

    def total(attribute: str) -> int:
        return sum(int(suite.attrib.get(attribute, "0")) for suite in suites)

    return JUnitCounts(
        tests=total("tests"),
        failures=total("failures"),
        errors=total("errors"),
        skipped=total("skipped"),
        duration_seconds=round(
            sum(float(suite.attrib.get("time", "0")) for suite in suites),
            3,
        ),
    )


def _json_outcome(path: Path) -> TrendOutcome | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    if isinstance(status, str):
        normalized = status.upper()
        for candidate in (
            "PASS",
            "PARTIAL",
            "FAILED",
            "NOT RUN",
            "BLOCKED",
            "DEFERRED",
        ):
            if normalized == candidate:
                return candidate
    if payload.get("passed") is True:
        return "PASS"
    if payload.get("passed") is False:
        return "FAILED"
    if isinstance(payload.get("all_passed"), bool):
        return "PASS" if payload["all_passed"] else "FAILED"
    return None


def discover_checks(artifacts_root: Path) -> tuple[TrendCheck, ...]:
    """Discover JUnit and status JSON evidence without trusting log text."""

    checks: list[TrendCheck] = []
    for path in sorted(artifacts_root.rglob("*.xml")):
        if "junit" not in path.name.casefold():
            continue
        try:
            counts = parse_junit(path)
        except (OSError, ValueError, ElementTree.ParseError):
            continue
        outcome: TrendOutcome = (
            "FAILED" if counts.failures or counts.errors else "PASS"
        )
        checks.append(
            TrendCheck(
                name=f"junit:{path.stem}",
                outcome=outcome,
                evidence=str(path),
                counts=counts,
            )
        )

    for path in sorted(artifacts_root.rglob("*.json")):
        json_outcome = _json_outcome(path)
        if json_outcome is None:
            continue
        checks.append(
            TrendCheck(
                name=f"json:{path.parent.name}/{path.stem}",
                outcome=json_outcome,
                evidence=str(path),
            )
        )
    return tuple(checks)


def build_trend_point(
    *,
    run_id: str,
    commit: str,
    checks: Iterable[TrendCheck],
) -> TrendPoint:
    return TrendPoint(
        run_id=run_id,
        commit=commit,
        generated_at=datetime.now(UTC),
        checks=tuple(checks),
    )


def append_history(
    history: TrendHistory,
    point: TrendPoint,
    *,
    max_points: int = 100,
) -> TrendHistory:
    """Replace an existing run id and retain a bounded history."""

    retained = [item for item in history.points if item.run_id != point.run_id]
    retained.append(point)
    return TrendHistory(points=tuple(retained[-max_points:]))


def load_history(path: Path) -> TrendHistory:
    if not path.is_file():
        return TrendHistory()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TrendHistory.model_validate(payload)


def render_trend_html(history: TrendHistory) -> str:
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{point.generated_at.isoformat()}</td>"
            f"<td><code>{point.commit[:12]}</code></td>"
            f"<td>{point.overall}</td>"
            f"<td>{len(point.checks)}</td>"
            "</tr>"
        )
        for point in reversed(history.points)
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Quality Engineering Lab Trends</title>"
        "<style>body{font-family:system-ui;margin:32px}"
        "table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:8px;text-align:left}</style>"
        "</head><body><h1>Quality Trend</h1>"
        "<table><thead><tr><th>Generated</th><th>Commit</th>"
        "<th>Overall</th><th>Checks</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></body></html>"
    )
