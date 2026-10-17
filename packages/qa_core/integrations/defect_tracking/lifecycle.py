"""Explicit defect states and human-approved transitions."""

from __future__ import annotations

from enum import StrEnum


class DefectState(StrEnum):
    """States used by local drafts and external issue trackers."""

    DRAFT = "draft"
    NEW = "new"
    TRIAGE = "triage"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    READY_FOR_VERIFICATION = "ready_for_verification"
    VERIFIED = "verified"
    CLOSED = "closed"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    WONT_FIX = "wont_fix"
    REOPENED = "reopened"


_TRANSITIONS: dict[DefectState, frozenset[DefectState]] = {
    DefectState.DRAFT: frozenset({DefectState.NEW}),
    DefectState.NEW: frozenset(
        {
            DefectState.TRIAGE,
            DefectState.DUPLICATE,
            DefectState.REJECTED,
            DefectState.DEFERRED,
            DefectState.WONT_FIX,
        }
    ),
    DefectState.TRIAGE: frozenset(
        {
            DefectState.CONFIRMED,
            DefectState.DUPLICATE,
            DefectState.REJECTED,
            DefectState.DEFERRED,
            DefectState.WONT_FIX,
        }
    ),
    DefectState.CONFIRMED: frozenset({DefectState.IN_PROGRESS}),
    DefectState.IN_PROGRESS: frozenset({DefectState.READY_FOR_VERIFICATION}),
    DefectState.READY_FOR_VERIFICATION: frozenset(
        {DefectState.VERIFIED, DefectState.REOPENED}
    ),
    DefectState.VERIFIED: frozenset({DefectState.CLOSED}),
    DefectState.REOPENED: frozenset({DefectState.IN_PROGRESS}),
    DefectState.CLOSED: frozenset(),
    DefectState.DUPLICATE: frozenset(),
    DefectState.REJECTED: frozenset(),
    DefectState.DEFERRED: frozenset({DefectState.TRIAGE}),
    DefectState.WONT_FIX: frozenset(),
}


def allowed_transitions(state: DefectState) -> frozenset[DefectState]:
    """Return the states reachable from ``state``."""

    return _TRANSITIONS[state]


def require_transition(
    current: DefectState,
    target: DefectState,
    *,
    approved_by: str,
) -> None:
    """Reject invalid or unattended state changes.

    The lifecycle boundary is intentionally small: every move needs a named
    human approver, and there is no automated path to ``closed``.
    """

    if not approved_by.strip():
        raise ValueError("defect transitions require a human approver")
    if target not in allowed_transitions(current):
        raise ValueError(f"cannot transition defect from {current} to {target}")
