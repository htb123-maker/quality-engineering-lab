"""Contracts for bounded fault injection and recovery evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from qa_core.e2e import (
    FaultSpec,
    FaultType,
    RecoveryContext,
    RecoveryJourney,
    RecoveryPolicy,
    RecoveryStepFailure,
)


def _context(tmp_path: Path) -> RecoveryContext:
    return RecoveryContext(
        run_id="run24",
        worker_id="gw0",
        test_id="E2E-W24-001",
        scenario_id="RECOVERY-API-NETWORK",
        platform="api",
        artifact_dir=tmp_path,
    )


def _spec(*, timeout_seconds: float = 1.0) -> FaultSpec:
    return FaultSpec(
        fault_type=FaultType.NETWORK_LATENCY,
        target="sut-api-gw0",
        expected_boundary="read timeout or bounded retry",
        timeout_seconds=timeout_seconds,
        parameters=(("latency_ms", 300),),
    )


@pytest.mark.unit
def test_recovery_journey_removes_fault_and_writes_manifest(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def observe() -> str:
        calls.append("observe")
        return "timed out"

    def verify(state: dict[str, str]) -> None:
        assert state == {"status": "active"}

    result = RecoveryJourney(
        baseline=lambda: {"status": "active"},
        inject=lambda: calls.append("inject"),
        observe=observe,
        remove=lambda: calls.append("remove"),
        probe=lambda: {"status": "active"},
        is_recovered=lambda state: state["status"] == "active",
        verify=verify,
    ).execute(_context(tmp_path), _spec())

    assert calls == ["inject", "observe", "remove"]
    assert result.attempts == 1
    assert result.manifest_path.exists()
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["fault"]["type"] == "network_latency"
    assert payload["fault"]["parameters"] == {"latency_ms": 300}
    assert payload["baseline"] == {"status": "active"}
    assert payload["recovered"] == {"status": "active"}
    assert payload["cleanup"]["attempted"] is True


@pytest.mark.unit
def test_baseline_failure_does_not_inject_or_remove(tmp_path: Path) -> None:
    calls: list[str] = []

    def fail_baseline() -> dict[str, str]:
        raise RuntimeError("baseline unavailable")

    with pytest.raises(RecoveryStepFailure) as error:
        RecoveryJourney(
            baseline=fail_baseline,
            inject=lambda: calls.append("inject"),
            observe=lambda: calls.append("observe"),
            remove=lambda: calls.append("remove"),
            probe=lambda: {"status": "active"},
            is_recovered=lambda state: True,
            verify=lambda state: None,
        ).execute(_context(tmp_path), _spec())

    assert error.value.step_id == "baseline"
    assert calls == []
    assert error.value.manifest_path is not None
    payload = json.loads(error.value.manifest_path.read_text(encoding="utf-8"))
    assert payload["cleanup"] == {"attempted": False, "error_type": None, "error_message": None}


@pytest.mark.unit
def test_injection_failure_still_attempts_removal(tmp_path: Path) -> None:
    removed: list[bool] = []

    def fail_injection() -> None:
        raise ConnectionError("proxy rejected toxic")

    with pytest.raises(RecoveryStepFailure) as error:
        RecoveryJourney(
            baseline=lambda: "active",
            inject=fail_injection,
            observe=lambda: "not reached",
            remove=lambda: removed.append(True),
            probe=lambda: "active",
            is_recovered=lambda state: True,
            verify=lambda state: None,
        ).execute(_context(tmp_path), _spec())

    assert error.value.step_id == "inject"
    assert removed == [True]


@pytest.mark.unit
def test_observation_failure_removes_fault_and_preserves_primary_failure(
    tmp_path: Path,
) -> None:
    removed: list[bool] = []

    def fail_observation() -> object:
        raise TimeoutError("expected fault boundary")

    with pytest.raises(RecoveryStepFailure) as error:
        RecoveryJourney(
            baseline=lambda: "active",
            inject=lambda: None,
            observe=fail_observation,
            remove=lambda: removed.append(True),
            probe=lambda: "active",
            is_recovered=lambda state: True,
            verify=lambda state: None,
        ).execute(_context(tmp_path), _spec())

    assert error.value.step_id == "observe"
    assert removed == [True]


@pytest.mark.unit
def test_recovery_retries_transport_errors_without_fixed_sleep(
    tmp_path: Path,
) -> None:
    now = 0.0
    attempts: list[int] = []

    def monotonic() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    def probe() -> str:
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise ConnectionError("service still restarting")
        return "active"

    result = RecoveryJourney(
        baseline=lambda: "active",
        inject=lambda: None,
        observe=lambda: "connection reset",
        remove=lambda: None,
        probe=probe,
        is_recovered=lambda state: state == "active",
        verify=lambda state: None,
        policy=RecoveryPolicy(poll_interval_seconds=0.25),
        sleep=sleep,
        monotonic=monotonic,
    ).execute(_context(tmp_path), _spec(timeout_seconds=1.0))

    assert attempts == [1, 2, 3]
    assert result.attempts == 3
    assert now == 0.5


@pytest.mark.unit
def test_recovery_timeout_reports_attempts_and_last_error(
    tmp_path: Path,
) -> None:
    now = 0.0

    def monotonic() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    def probe() -> str:
        raise ConnectionError("still unavailable")

    with pytest.raises(RecoveryStepFailure) as error:
        RecoveryJourney(
            baseline=lambda: "active",
            inject=lambda: None,
            observe=lambda: "unavailable",
            remove=lambda: None,
            probe=probe,
            is_recovered=lambda state: True,
            verify=lambda state: None,
            policy=RecoveryPolicy(poll_interval_seconds=0.25),
            sleep=sleep,
            monotonic=monotonic,
        ).execute(_context(tmp_path), _spec(timeout_seconds=0.5))

    assert error.value.step_id == "recover"
    assert isinstance(error.value.cause, TimeoutError)
    assert "after 3 attempts" in str(error.value.cause)
    assert error.value.manifest_path is not None
    payload = json.loads(error.value.manifest_path.read_text(encoding="utf-8"))
    assert payload["attempts"] == 3
    assert payload["last_probe_error"]["type"] == "ConnectionError"


@pytest.mark.unit
def test_cleanup_failure_does_not_mask_primary_failure(tmp_path: Path) -> None:
    def fail_observation() -> object:
        raise RuntimeError("observed fault")

    def fail_cleanup() -> None:
        raise OSError("toxic removal failed")

    with pytest.raises(RecoveryStepFailure) as error:
        RecoveryJourney(
            baseline=lambda: "active",
            inject=lambda: None,
            observe=fail_observation,
            remove=fail_cleanup,
            probe=lambda: "active",
            is_recovered=lambda state: True,
            verify=lambda state: None,
        ).execute(_context(tmp_path), _spec())

    assert error.value.step_id == "observe"
    assert isinstance(error.value.cause, RuntimeError)
    assert error.value.manifest_path is not None
    payload = json.loads(error.value.manifest_path.read_text(encoding="utf-8"))
    assert payload["cleanup"]["error_type"] == "OSError"


@pytest.mark.unit
def test_recovery_manifest_redacts_secret_keys(tmp_path: Path) -> None:
    result = RecoveryJourney[dict[str, object], str](
        baseline=lambda: {
            "status": "active",
            "access_token": "do-not-persist",
            "nested": {"password": "also-secret"},
        },
        inject=lambda: None,
        observe=lambda: "unauthorized",
        remove=lambda: None,
        probe=lambda: {"status": "active", "access_token": "do-not-persist"},
        is_recovered=lambda state: state["status"] == "active",
        verify=lambda state: None,
    ).execute(_context(tmp_path), _spec())

    payload = result.manifest_path.read_text(encoding="utf-8")

    assert "do-not-persist" not in payload
    assert "also-secret" not in payload
