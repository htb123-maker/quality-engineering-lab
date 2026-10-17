"""Defect lifecycle rules shared by tracker adapters."""

from qa_core.integrations.defect_tracking.lifecycle import (
    DefectState,
    allowed_transitions,
    require_transition,
)

__all__ = [
    "DefectState",
    "allowed_transitions",
    "require_transition",
]
