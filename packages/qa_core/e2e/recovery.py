"""Bounded fault injection, removal, recovery, and evidence orchestration."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel

from qa_core.e2e.faults import FaultSpec

RecoveryPlatform = Literal["api", "android", "ios"]
_SECRET_KEY = re.compile(
    r"(access[_-]?key|api[_-]?key|password|private[_-]?key|secret|token)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RecoveryContext:
    """Correlation identity for one fault-and-recovery journey."""

    run_id: str
    worker_id: str
    test_id: str
    scenario_id: str
    platform: RecoveryPlatform
    artifact_dir: Path

    def __post_init__(self) -> None:
        for name in ("run_id", "worker_id", "test_id", "scenario_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        if self.platform not in {"api", "android", "ios"}:
            raise ValueError("recovery platform must be api, android, or ios")


@dataclass(frozen=True, slots=True)
class RecoveryPolicy:
    """Polling behavior used while waiting for a recovered business state."""

    poll_interval_seconds: float = 0.1

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")


@dataclass(frozen=True, slots=True)
class RecoveryResult[RecoveryState, ObservedState]:
    """Verified baseline and recovered state plus the evidence manifest."""

    spec: FaultSpec
    baseline: RecoveryState
    observed: ObservedState
    recovered: RecoveryState
    attempts: int
    elapsed_seconds: float
    manifest_path: Path


class RecoveryStepFailure(RuntimeError):
    """Recovery failure with a stable step identity and manifest location."""

    def __init__(
        self,
        context: RecoveryContext,
        step_id: str,
        cause: BaseException,
    ) -> None:
        self.context = context
        self.step_id = step_id
        self.cause = cause
        self.manifest_path: Path | None = None
        super().__init__(
            f"Recovery scenario {context.scenario_id!r} failed at {step_id!r}: "
            f"{type(cause).__name__}: {cause}"
        )


class RecoveryJourney[RecoveryState, ObservedState]:
    """Prove baseline -> fault -> observed boundary -> remove -> recover -> verify."""

    def __init__(
        self,
        *,
        baseline: Callable[[], RecoveryState],
        inject: Callable[[], None],
        observe: Callable[[], ObservedState],
        remove: Callable[[], None],
        probe: Callable[[], RecoveryState],
        is_recovered: Callable[[RecoveryState], bool],
        verify: Callable[[RecoveryState], None],
        policy: RecoveryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._baseline = baseline
        self._inject = inject
        self._observe = observe
        self._remove = remove
        self._probe = probe
        self._is_recovered = is_recovered
        self._verify = verify
        self._policy = policy or RecoveryPolicy()
        self._sleep = sleep
        self._monotonic = monotonic

    def execute(
        self,
        context: RecoveryContext,
        spec: FaultSpec,
    ) -> RecoveryResult[RecoveryState, ObservedState]:
        """Run one journey and always attempt fault removal after injection."""

        started_at = self._monotonic()
        injection_attempted = False
        removal_attempted = False
        cleanup_error: BaseException | None = None
        step_failure: RecoveryStepFailure | None = None
        baseline: RecoveryState | None = None
        observed: ObservedState | None = None
        recovered: RecoveryState | None = None
        last_observation: object | None = None
        last_probe_error: BaseException | None = None
        attempts = 0
        recovery_elapsed_seconds: float | None = None

        try:
            try:
                baseline = self._baseline()
            except Exception as exc:
                raise RecoveryStepFailure(context, "baseline", exc) from exc

            injection_attempted = True
            try:
                self._inject()
            except Exception as exc:
                raise RecoveryStepFailure(context, "inject", exc) from exc

            try:
                observed = self._observe()
            except Exception as exc:
                raise RecoveryStepFailure(context, "observe", exc) from exc

            removal_attempted = True
            try:
                self._remove()
            except Exception as exc:
                raise RecoveryStepFailure(context, "remove", exc) from exc

            recovery_started_at = self._monotonic()
            try:
                (
                    recovered,
                    attempts,
                    last_observation,
                    last_probe_error,
                ) = self._wait_until_recovered(spec)
            except Exception as exc:
                if isinstance(exc, _RecoveryWaitTimeout):
                    attempts = exc.attempts
                    last_probe_error = exc.last_error
                raise RecoveryStepFailure(context, "recover", exc) from exc
            finally:
                recovery_elapsed_seconds = (
                    self._monotonic() - recovery_started_at
                )

            try:
                self._verify(recovered)
            except Exception as exc:
                raise RecoveryStepFailure(context, "verify", exc) from exc
        except RecoveryStepFailure as exc:
            step_failure = exc
        except BaseException as exc:
            step_failure = RecoveryStepFailure(context, "journey", exc)
        finally:
            if injection_attempted and not removal_attempted:
                removal_attempted = True
                try:
                    self._remove()
                except BaseException as exc:
                    cleanup_error = exc

            elapsed_seconds = self._monotonic() - started_at
            manifest_path = _write_manifest(
                context,
                spec=spec,
                baseline=baseline,
                observed=observed,
                recovered=recovered,
                last_observation=last_observation,
                last_probe_error=last_probe_error,
                attempts=attempts,
                cleanup_attempted=removal_attempted,
                cleanup_error=cleanup_error,
                failure=step_failure,
                elapsed_seconds=elapsed_seconds,
                recovery_elapsed_seconds=recovery_elapsed_seconds,
            )
            if step_failure is not None:
                step_failure.manifest_path = manifest_path

        if step_failure is not None:
            raise step_failure
        if cleanup_error is not None:
            failure = RecoveryStepFailure(context, "cleanup", cleanup_error)
            failure.manifest_path = manifest_path
            raise failure
        if baseline is None or recovered is None:
            raise RuntimeError("successful recovery journey did not produce state")

        return RecoveryResult(
            spec=spec,
            baseline=baseline,
            observed=cast(ObservedState, observed),
            recovered=recovered,
            attempts=attempts,
            elapsed_seconds=elapsed_seconds,
            manifest_path=manifest_path,
        )

    def _wait_until_recovered(
        self,
        spec: FaultSpec,
    ) -> tuple[RecoveryState, int, object | None, BaseException | None]:
        deadline = self._monotonic() + spec.timeout_seconds
        attempts = 0
        last_observation: object | None = None
        last_error: BaseException | None = None

        while True:
            attempts += 1
            try:
                candidate = self._probe()
            except Exception as exc:
                last_error = exc
            else:
                last_observation = candidate
                if self._is_recovered(candidate):
                    return candidate, attempts, last_observation, last_error

            now = self._monotonic()
            if now >= deadline:
                detail = (
                    f"last error: {type(last_error).__name__}: {last_error}"
                    if last_error is not None
                    else f"last observation: {last_observation!r}"
                )
                raise _RecoveryWaitTimeout(
                    f"recovery did not complete within {spec.timeout_seconds:.3f}s "
                    f"after {attempts} attempts; {detail}",
                    attempts=attempts,
                    last_error=last_error,
                )
            self._sleep(min(self._policy.poll_interval_seconds, deadline - now))


class _RecoveryWaitTimeout(TimeoutError):
    """Internal timeout carrying the final evidence values."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_error: BaseException | None,
    ) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(message)


def _write_manifest(
    context: RecoveryContext,
    *,
    spec: FaultSpec,
    baseline: object | None,
    observed: object | None,
    recovered: object | None,
    last_observation: object | None,
    last_probe_error: BaseException | None,
    attempts: int,
    cleanup_attempted: bool,
    cleanup_error: BaseException | None,
    failure: BaseException | None,
    elapsed_seconds: float,
    recovery_elapsed_seconds: float | None,
) -> Path:
    context.artifact_dir.mkdir(parents=True, exist_ok=True)
    path = context.artifact_dir / "recovery-result.json"
    payload: dict[str, object] = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "run_id": context.run_id,
        "worker_id": context.worker_id,
        "test_id": context.test_id,
        "scenario_id": context.scenario_id,
        "platform": context.platform,
        "fault": {
            "type": spec.fault_type.value,
            "target": spec.target,
            "expected_boundary": spec.expected_boundary,
            "timeout_seconds": spec.timeout_seconds,
            "cleanup_action": spec.cleanup_action,
            "parameters": spec.parameter_map,
        },
        "baseline": _json_safe(baseline),
        "observed": _json_safe(observed),
        "recovered": _json_safe(recovered),
        "last_observation": _json_safe(last_observation),
        "last_probe_error": (
            {
                "type": type(last_probe_error).__name__,
                "message": _redact(str(last_probe_error)),
            }
            if last_probe_error is not None
            else None
        ),
        "attempts": attempts,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "recovery_elapsed_seconds": (
            round(recovery_elapsed_seconds, 6)
            if recovery_elapsed_seconds is not None
            else None
        ),
        "cleanup": {
            "attempted": cleanup_attempted,
            "error_type": type(cleanup_error).__name__ if cleanup_error else None,
            "error_message": _redact(str(cleanup_error)) if cleanup_error else None,
        },
        "failure_step": (
            failure.step_id if isinstance(failure, RecoveryStepFailure) else None
        ),
        "failure_type": type(failure.cause).__name__ if isinstance(
            failure, RecoveryStepFailure
        ) else (type(failure).__name__ if failure is not None else None),
        "failure_message": (
            _redact(str(failure.cause))
            if isinstance(failure, RecoveryStepFailure)
            else (_redact(str(failure)) if failure is not None else None)
        ),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return _redact(value) if isinstance(value, str) else value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): (
                "<redacted>"
                if _SECRET_KEY.search(str(key)) or "udid" in str(key).casefold()
                else _json_safe(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return f"<{type(value).__name__}>"


def _redact(value: str) -> str:
    return _SECRET_KEY.sub("<redacted>", value)
