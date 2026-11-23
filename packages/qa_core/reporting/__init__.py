"""Reporting and defect-traceability helpers."""

from qa_core.reporting.defect_draft import (
    DefectDraft,
    DefectEvidence,
    JsonlDefectDraftStore,
    build_defect_draft,
)
from qa_core.reporting.defect_fingerprint import DefectFingerprint
from qa_core.reporting.governance import (
    QualityGovernance,
    QualityOwners,
    QuarantineEntry,
    load_quality_governance,
)
from qa_core.reporting.leak_report import (
    EnvironmentSnapshot,
    LeakVerdict,
    compare_snapshots,
    parse_pytest_summary,
)
from qa_core.reporting.quality_trends import (
    REQUIRED_PIPELINE_CHECKS,
    JUnitCounts,
    TrendCheck,
    TrendHistory,
    TrendOutcome,
    TrendPoint,
    append_history,
    build_trend_point,
    discover_checks,
    load_history,
    missing_required_checks,
    parse_junit,
    render_trend_html,
    with_required_check_placeholders,
)

__all__ = [
    "DefectDraft",
    "DefectEvidence",
    "DefectFingerprint",
    "EnvironmentSnapshot",
    "JsonlDefectDraftStore",
    "LeakVerdict",
    "QuarantineEntry",
    "QualityGovernance",
    "QualityOwners",
    "REQUIRED_PIPELINE_CHECKS",
    "JUnitCounts",
    "TrendCheck",
    "TrendHistory",
    "TrendOutcome",
    "TrendPoint",
    "append_history",
    "build_defect_draft",
    "build_trend_point",
    "compare_snapshots",
    "discover_checks",
    "load_history",
    "load_quality_governance",
    "missing_required_checks",
    "parse_junit",
    "parse_pytest_summary",
    "render_trend_html",
    "with_required_check_placeholders",
]
