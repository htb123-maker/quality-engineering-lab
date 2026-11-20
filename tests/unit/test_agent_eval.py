"""Week 32 read-only evidence triage agent contracts."""

from pathlib import Path

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


def test_golden_tasks_are_reproducible_and_evidence_linked() -> None:
    result = evaluate(PROJECT_ROOT / "ai" / "golden_tasks" / "week32.jsonl")

    assert result["tasks"] == 30
    assert result["accuracy"] == 1.0
    assert result["evidence_reference_rate"] == 1.0
    assert result["automatic_writes"] == 0
    assert result["false_pass_count"] == 0
    assert result["gate_acceptance_rate"] == 1.0
    assert result["human_review"]["status"] == "NOT RUN"
    assert result["human_review"]["acceptance_rate"] is None
    assert result["token_usage"] == 0
    assert result["cost_usd"] == 0.0
