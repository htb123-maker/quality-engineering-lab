"""Defect lifecycle rules shared by tracker adapters."""

from qa_core.integrations.defect_tracking.github_issues import (
    GitHubIssueAdapter,
    GitHubIssueReference,
    GitHubIssueRequest,
)
from qa_core.integrations.defect_tracking.lifecycle import (
    DefectState,
    allowed_transitions,
    require_transition,
)

__all__ = [
    "DefectState",
    "GitHubIssueAdapter",
    "GitHubIssueReference",
    "GitHubIssueRequest",
    "allowed_transitions",
    "require_transition",
]
