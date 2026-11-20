"""Read-only deterministic evidence triage agent baseline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

SignalState = Literal["PASS", "FAILED", "BLOCKED", "NOT RUN", "DEFERRED", "UNKNOWN"]
TriageOutcome = Literal["PASS", "FAILED", "BLOCKED", "INSUFFICIENT_EVIDENCE"]


@dataclass(frozen=True, slots=True)
class TriageFinding:
    """One evidence-linked finding with no write authority."""

    outcome: TriageOutcome
    suspected_layer: str
    confidence: float
    evidence: tuple[str, ...]
    requires_human_approval: bool
    reason: str


class EvidenceTriageAgent:
    """Classify structured CI evidence; never execute or modify a system."""

    _BLOCKING = frozenset({"BLOCKED", "NOT RUN", "DEFERRED"})

    def triage(
        self,
        *,
        signals: Mapping[str, SignalState],
        evidence: Sequence[str],
    ) -> TriageFinding:
        sources = tuple(sorted(set(item for item in evidence if item.strip())))
        if not sources or not signals or "UNKNOWN" in signals.values():
            return TriageFinding(
                outcome="INSUFFICIENT_EVIDENCE",
                suspected_layer="evidence",
                confidence=1.0,
                evidence=sources,
                requires_human_approval=True,
                reason="required evidence or a known signal state is missing",
            )

        failed = sorted(name for name, state in signals.items() if state == "FAILED")
        if failed:
            return TriageFinding(
                outcome="FAILED",
                suspected_layer=failed[0],
                confidence=1.0,
                evidence=sources,
                requires_human_approval=True,
                reason=f"failed signal(s): {', '.join(failed)}",
            )

        blocked = sorted(
            name for name, state in signals.items() if state in self._BLOCKING
        )
        if blocked:
            return TriageFinding(
                outcome="BLOCKED",
                suspected_layer=blocked[0],
                confidence=1.0,
                evidence=sources,
                requires_human_approval=True,
                reason=f"incomplete signal(s): {', '.join(blocked)}",
            )

        unknown_states = sorted(
            f"{name}={state}"
            for name, state in signals.items()
            if state != "PASS"
        )
        if unknown_states:
            return TriageFinding(
                outcome="INSUFFICIENT_EVIDENCE",
                suspected_layer="evidence",
                confidence=1.0,
                evidence=sources,
                requires_human_approval=True,
                reason=f"unsupported signal state(s): {', '.join(unknown_states)}",
            )

        return TriageFinding(
            outcome="PASS",
            suspected_layer="none",
            confidence=1.0,
            evidence=sources,
            requires_human_approval=False,
            reason="all required signals are PASS and evidence is present",
        )
