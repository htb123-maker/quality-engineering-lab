"""Unit tests for local, human-reviewable defect drafts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from qa_core.integrations.defect_tracking import (
    DefectState,
    allowed_transitions,
    require_transition,
)
from qa_core.plugins.defect_drafts import _classify_failure
from qa_core.reporting import (
    DefectDraft,
    DefectEvidence,
    DefectFingerprint,
    JsonlDefectDraftStore,
    build_defect_draft,
)


def _fingerprint(*, error_signature: str = "assert 503 == 200") -> DefectFingerprint:
    return DefectFingerprint(
        test_id="tests/api/test_health.py::test_ready",
        failure_type="assertion",
        top_stack_frames=("tests/api/test_health.py:12 in test_ready",),
        error_signature=error_signature,
        platform="api",
        device_class="container",
        app_version_bucket="sut-local",
        environment="local",
    )


def _draft(fingerprint: DefectFingerprint) -> DefectDraft:
    return build_defect_draft(
        fingerprint=fingerprint,
        expected="HTTP 200",
        actual="assert 503 == 200",
        reproduction_steps=("pytest tests/api/test_health.py::test_ready",),
        evidence=DefectEvidence(
            test_id=fingerprint.test_id,
            pytest_nodeid=fingerprint.test_id,
            commit="abc123",
            environment="local",
            command="pytest tests/api/test_health.py::test_ready",
            first_failure="AssertionError: assert 503 == 200",
        ),
    )


@pytest.mark.unit
def test_draft_is_idempotent_and_always_requires_human_approval(tmp_path: Path) -> None:
    store = JsonlDefectDraftStore(tmp_path / "defects.jsonl")
    draft = _draft(_fingerprint())

    assert store.save(draft) is True
    assert store.save(draft) is False
    assert len(store.read_all()) == 1
    assert store.read_all()[0].requires_human_approval is True
    assert store.read_all()[0].automatically_created_issue is False


@pytest.mark.unit
def test_concurrent_draft_writes_remain_valid_json_lines(tmp_path: Path) -> None:
    store = JsonlDefectDraftStore(tmp_path / "defects.jsonl")
    drafts = [
        _draft(_fingerprint(error_signature=f"assert {index} == 200"))
        for index in range(20)
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(store.save, drafts))

    assert results.count(True) == 20
    assert len(store.read_all()) == 20


@pytest.mark.unit
def test_similarity_prefers_exact_digest_then_test_and_signature(tmp_path: Path) -> None:
    store = JsonlDefectDraftStore(tmp_path / "defects.jsonl")
    original = _draft(_fingerprint())
    other = _draft(_fingerprint(error_signature="assert 500 == 200"))
    store.save(original)
    store.save(other)

    exact = store.find_similar(original)
    assert [candidate.fingerprint.digest for candidate in exact] == [
        original.fingerprint.digest
    ]


@pytest.mark.unit
def test_failure_classification_separates_timeout_and_connection() -> None:
    assert _classify_failure(AssertionError("status mismatch")) == "assertion"
    assert _classify_failure(httpx.ReadTimeout("slow")) == "timeout"
    assert _classify_failure(httpx.ConnectError("refused")) == "connection"
    assert _classify_failure(ValueError("bad value")) == "unknown"


@pytest.mark.unit
def test_lifecycle_requires_valid_human_approved_transitions() -> None:
    require_transition(
        DefectState.DRAFT,
        DefectState.NEW,
        approved_by="qa-reviewer",
    )
    assert DefectState.NEW not in allowed_transitions(DefectState.VERIFIED)
    assert DefectState.CLOSED in allowed_transitions(DefectState.VERIFIED)

    with pytest.raises(ValueError, match="human approver"):
        require_transition(DefectState.DRAFT, DefectState.NEW, approved_by=" ")
    with pytest.raises(ValueError, match="cannot transition"):
        require_transition(
            DefectState.DRAFT,
            DefectState.CLOSED,
            approved_by="qa-reviewer",
        )
