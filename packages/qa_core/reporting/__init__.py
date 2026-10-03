"""Reporting and defect-traceability helpers."""

from qa_core.reporting.defect_fingerprint import DefectFingerprint
from qa_core.reporting.leak_report import (
    EnvironmentSnapshot,
    LeakVerdict,
    compare_snapshots,
    parse_pytest_summary,
)

__all__ = [
    "DefectFingerprint",
    "EnvironmentSnapshot",
    "LeakVerdict",
    "compare_snapshots",
    "parse_pytest_summary",
]
