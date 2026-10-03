"""Unit tests for deterministic defect fingerprints."""

import pytest
from pydantic import ValidationError
from qa_core.reporting import DefectFingerprint


def _fingerprint(**overrides: object) -> DefectFingerprint:
    values: dict[str, object] = {
        "test_id": "SMOKE-API-SUT-001",
        "failure_type": "assertion",
        "top_stack_frames": (
            "tests/api/test_sut_smoke.py:31 in test_sut_readiness",
            "httpx/_client.py:914 in request",
        ),
        "error_signature": "assert 503 == 200",
        "platform": "api",
        "device_class": "container",
        "app_version_bucket": "sut-0.1",
        "environment": "local",
    }
    values.update(overrides)
    return DefectFingerprint.model_validate(values)


@pytest.mark.unit
def test_fingerprint_normalizes_whitespace_and_remains_stable() -> None:
    first = _fingerprint(error_signature="  assert   503 == 200  ")
    second = _fingerprint(error_signature="assert 503 == 200")

    assert first.digest == second.digest
    assert first.short_id.startswith("FPR-")
    assert len(first.digest) == 64


@pytest.mark.unit
def test_fingerprint_changes_when_root_cause_boundary_changes() -> None:
    local_api = _fingerprint()
    ci_database = _fingerprint(
        platform="infrastructure",
        failure_type="connection",
        error_signature="OperationalError: connection refused",
        environment="ci",
    )

    assert local_api.digest != ci_database.digest


@pytest.mark.unit
def test_fingerprint_rejects_unbounded_stack_frames() -> None:
    with pytest.raises(ValidationError, match="at most five frames"):
        _fingerprint(top_stack_frames=tuple(f"frame-{index}" for index in range(6)))
