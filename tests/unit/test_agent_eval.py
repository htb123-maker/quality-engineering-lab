"""Week 32 read-only evidence triage agent contracts."""

import json
from pathlib import Path

import pytest
from qa_core.reporting import discover_checks

from ai.agents.evidence_triage import EvidenceTriageAgent
from ai.evals.run_golden_tasks import evaluate

PROJECT_ROOT = Path(__file__).parents[2]


def test_agent_passes_only_complete_evidence() -> None:
    finding = EvidenceTriageAgent().triage(
        signals={"api": "PASS", "android": "PASS"},
        evidence=("api-junit", "android-junit"),
    )

    assert finding.outcome == "PASS"
    assert finding.requires_human_approval is False


def test_agent_fails_closed_when_evidence_is_missing() -> None:
    finding = EvidenceTriageAgent().triage(
        signals={"api": "PASS"},
        evidence=(),
    )

    assert finding.outcome == "INSUFFICIENT_EVIDENCE"
    assert finding.requires_human_approval is True


def test_agent_prioritizes_failure_over_blocked_platform() -> None:
    finding = EvidenceTriageAgent().triage(
        signals={"api": "FAILED", "ios": "BLOCKED"},
        evidence=("api-junit", "ios-status"),
    )

    assert finding.outcome == "FAILED"
    assert finding.suspected_layer == "api"


def test_golden_tasks_are_reproducible_and_evidence_linked(
    tmp_path: Path,
) -> None:
    result = evaluate(
        PROJECT_ROOT / "ai" / "golden_tasks" / "week32.jsonl",
        PROJECT_ROOT / "ai" / "evals" / "week32-human-review.json",
    )

    assert result["tasks"] == 30
    assert result["status"] == "PASS"
    assert result["accuracy"] == 1.0
    assert result["evidence_reference_rate"] == 1.0
    assert result["automatic_writes"] == 0
    assert result["false_pass_count"] == 0
    assert result["gate_acceptance_rate"] == 1.0
    assert result["human_review"]["status"] == "APPROVED"
    assert result["human_review"]["reviewed"] == 30
    assert result["human_review"]["acceptance_rate"] == 1.0
    assert result["human_review"]["modification_rate"] == 0.0
    assert result["token_usage"] == 0
    assert result["cost_usd"] == 0.0

    output = tmp_path / "week32-ai-eval" / "agent-eval.json"
    output.parent.mkdir()
    output.write_text(json.dumps(result), encoding="utf-8")
    assert [(check.name, check.outcome) for check in discover_checks(tmp_path)] == [
        ("json:week32-ai-eval/agent-eval", "PASS")
    ]


def test_human_review_requires_every_golden_task(tmp_path: Path) -> None:
    payload = json.loads(
        (PROJECT_ROOT / "ai" / "evals" / "week32-human-review.json").read_text(
            encoding="utf-8"
        )
    )
    payload["decisions"].pop()
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="cover every Golden Task"):
        evaluate(
            PROJECT_ROOT / "ai" / "golden_tasks" / "week32.jsonl",
            review_path,
        )
