"""Convert collected CI artifacts into read-only Agent monitoring findings."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from qa_core.reporting import parse_junit

from ai.agents.evidence_triage import (
    EvidenceTriageAgent,
    SignalState,
    TriageFinding,
)

REQUIRED_SIGNALS = (
    "quality",
    "sut",
    "api",
    "android",
    "android_business",
    "ios_simulator",
    "performance",
    "agent_eval",
)


@dataclass(frozen=True, slots=True)
class ArtifactSignals:
    """Normalized signals and their concrete source files."""

    signals: dict[str, SignalState]
    evidence: tuple[str, ...]
    performance_evidence: tuple[str, ...]


def _find_file(root: Path, name: str) -> Path | None:
    matches = sorted(root.rglob(name), key=lambda path: (len(path.parts), str(path)))
    return matches[0] if matches else None


def _junit_state(path: Path | None) -> SignalState:
    if path is None:
        return "UNKNOWN"
    try:
        counts = parse_junit(path)
    except (OSError, ValueError):
        return "UNKNOWN"
    if counts.failures or counts.errors:
        return "FAILED"
    return "PASS"


def _json_state(path: Path | None, *, key: str) -> SignalState:
    if path is None:
        return "UNKNOWN"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "UNKNOWN"
    if not isinstance(payload, dict):
        return "UNKNOWN"
    value = payload.get(key)
    if isinstance(value, bool):
        return "PASS" if value else "FAILED"
    if isinstance(value, str):
        normalized = value.upper()
        if normalized in {"PASS", "FAILED", "BLOCKED", "NOT RUN", "DEFERRED"}:
            return cast(SignalState, normalized)
    return "UNKNOWN"


def collect_artifact_signals(root: Path) -> ArtifactSignals:
    """Map standard pipeline artifacts onto one deterministic signal set."""

    paths: dict[str, Path | None] = {
        "quality": _find_file(root, "quality-junit.xml"),
        "sut": _find_file(root, "sut-junit.xml"),
        "api": _find_file(root, "api-junit.xml"),
        "android": _find_file(root, "android-junit.xml"),
        "android_business": _find_file(root, "android-business-junit.xml"),
        "ios_simulator": _find_file(root, "ios-simulator-junit.xml"),
        "performance": _find_file(root, "result.json"),
        "agent_eval": _find_file(root, "agent-eval.json"),
    }
    signals: dict[str, SignalState] = {}
    evidence: list[str] = []
    performance_evidence: list[str] = []
    for name, path in paths.items():
        if path is None:
            signals[name] = "UNKNOWN"
            continue
        if name == "performance":
            state = _json_state(path, key="slo_passed")
            performance_evidence.append(str(path))
        elif name == "agent_eval":
            state = _json_state(path, key="status")
        else:
            state = _junit_state(path)
        signals[name] = state
        evidence.append(str(path))

    return ArtifactSignals(
        signals=signals,
        evidence=tuple(evidence),
        performance_evidence=tuple(performance_evidence),
    )


def _agent_payload(
    agent_id: str,
    finding: TriageFinding,
) -> dict[str, Any]:
    return {
        "id": agent_id,
        "outcome": finding.outcome,
        "suspected_layer": finding.suspected_layer,
        "confidence": finding.confidence,
        "evidence_paths": list(finding.evidence),
        "proposed_actions": (
            []
            if finding.outcome == "PASS"
            else [
                "Review the named evidence and preserve the failing status.",
                "Require human approval before changing thresholds or closing work.",
            ]
        ),
        "requires_human_approval": finding.requires_human_approval,
        "reason": finding.reason,
    }


def build_monitoring_report(
    artifacts_root: Path,
    *,
    run_id: str,
    commit: str,
    generated_at: float | None = None,
) -> dict[str, Any]:
    """Run the first two real monitoring agents over collected artifacts."""

    collected = collect_artifact_signals(artifacts_root)
    triage = EvidenceTriageAgent()
    ci_finding = triage.triage(
        signals=collected.signals,
        evidence=collected.evidence,
    )
    performance_finding = triage.triage(
        signals={"performance": collected.signals["performance"]},
        evidence=collected.performance_evidence,
    )
    findings = (
        _agent_payload("ci-monitor", ci_finding),
        _agent_payload("performance-monitor", performance_finding),
    )
    if "FAILED" in {ci_finding.outcome, performance_finding.outcome}:
        status = "FAILED"
    elif "INSUFFICIENT_EVIDENCE" in {
        ci_finding.outcome,
        performance_finding.outcome,
    }:
        status = "INSUFFICIENT_EVIDENCE"
    elif "BLOCKED" in {ci_finding.outcome, performance_finding.outcome}:
        status = "BLOCKED"
    else:
        status = "PASS"
    return {
        "schema_version": 1,
        "status": status,
        "run_id": run_id,
        "commit": commit,
        "generated_at": generated_at or time.time(),
        "signals": collected.signals,
        "missing_signals": [
            name
            for name in REQUIRED_SIGNALS
            if collected.signals.get(name) == "UNKNOWN"
        ],
        "agents": list(findings),
        "automatic_writes": 0,
        "requires_human_approval": any(
            finding["requires_human_approval"] for finding in findings
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fail-on-incomplete", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_monitoring_report(
        args.artifacts_root,
        run_id=args.run_id,
        commit=args.commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"agent-monitor status={report['status']} "
        f"missing={len(report['missing_signals'])} "
        f"agents={len(report['agents'])}"
    )
    if args.fail_on_incomplete and report["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
