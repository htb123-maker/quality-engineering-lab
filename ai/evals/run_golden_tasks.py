"""Evaluate the read-only evidence triage agent against Golden Tasks."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from ai.agents.evidence_triage import EvidenceTriageAgent, SignalState

KNOWN_SIGNALS = frozenset(
    {"PASS", "FAILED", "BLOCKED", "NOT RUN", "DEFERRED", "UNKNOWN"}
)


def _signals(payload: dict[str, Any]) -> dict[str, SignalState]:
    raw = payload.get("signals")
    if not isinstance(raw, dict):
        raise ValueError("golden task signals must be an object")
    invalid = {
        str(name): str(state)
        for name, state in raw.items()
        if str(state) not in KNOWN_SIGNALS
    }
    if invalid:
        raise ValueError(f"unknown signal states: {invalid}")
    return cast(
        dict[str, SignalState],
        {str(name): str(state) for name, state in raw.items()},
    )


def _percentile(values: Sequence[float], percentage: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentage / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (
        rank - lower
    )


def evaluate(tasks_path: Path) -> dict[str, Any]:
    agent = EvidenceTriageAgent()
    records: list[dict[str, Any]] = []
    latencies: list[float] = []
    for line in tasks_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        task = json.loads(line)
        started = time.perf_counter()
        finding = agent.triage(
            signals=_signals(task),
            evidence=task["evidence"],
        )
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        expected = str(task["expected"])
        evidence_ok = set(task["required_evidence"]).issubset(finding.evidence)
        records.append(
            {
                "task_id": task["id"],
                "expected": expected,
                "actual": finding.outcome,
                "correct": finding.outcome == expected,
                "evidence_ok": evidence_ok,
                "confidence": finding.confidence,
                "latency_ms": round(latency_ms, 4),
                "evidence": list(finding.evidence),
            }
        )

    correct = sum(bool(record["correct"]) for record in records)
    evidence_complete = sum(bool(record["evidence_ok"]) for record in records)
    false_pass_count = sum(
        bool(
            record["actual"] == "PASS"
            and record["expected"] != "PASS"
        )
        for record in records
    )
    gate_accepted = bool(records) and correct == len(records)
    return {
        "schema_version": 1,
        "agent": "evidence-triage-v1-deterministic",
        "tasks": len(records),
        "correct": correct,
        "accuracy": round(correct / len(records), 4) if records else 0.0,
        "evidence_reference_rate": (
            round(evidence_complete / len(records), 4) if records else 0.0
        ),
        "p95_latency_ms": round(_percentile(latencies, 95), 4),
        "token_usage": 0,
        "cost_usd": 0.0,
        "automatic_writes": 0,
        "false_pass_count": false_pass_count,
        "gate_acceptance_rate": 1.0 if gate_accepted else 0.0,
        "human_review": {
            "status": "NOT RUN",
            "reviewed": 0,
            "accepted": 0,
            "modified": 0,
            "acceptance_rate": None,
            "modification_rate": None,
        },
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tasks",
        type=Path,
        default=Path("ai/golden_tasks/week32.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/ai/week32/agent-eval.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = evaluate(args.tasks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"tasks={result['tasks']} accuracy={result['accuracy']} "
        f"evidence={result['evidence_reference_rate']} "
        f"p95_ms={result['p95_latency_ms']}"
    )
    return 0 if math.isclose(result["accuracy"], 1.0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
