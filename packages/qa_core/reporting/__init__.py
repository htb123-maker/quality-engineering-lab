"""Reporting and defect-traceability helpers."""

from qa_core.reporting.defect_draft import (
    DefectDraft,
    DefectEvidence,
    JsonlDefectDraftStore,
    build_defect_draft,
)
from qa_core.reporting.defect_fingerprint import DefectFingerprint
from qa_core.reporting.leak_report import (
    EnvironmentSnapshot,
    LeakVerdict,
    compare_snapshots,
    parse_pytest_summary,
)

__all__ = [
    "DefectDraft",
    "DefectEvidence",
    "DefectFingerprint",
    "EnvironmentSnapshot",
    "JsonlDefectDraftStore",
    "LeakVerdict",
    "build_defect_draft",
    "compare_snapshots",
    "parse_pytest_summary",
]
