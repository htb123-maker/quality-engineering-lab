"""Typed load profiles and deterministic performance objective checks."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

PerformanceMetric = Literal[
    "p50_response_time_ms",
    "p95_response_time_ms",
    "p99_response_time_ms",
    "requests_per_second",
    "duration_seconds",
    "error_rate",
    "total_requests",
]
ComparisonOperator = Literal["lte", "gte"]
AuthenticationMode = Literal["none", "password"]


class LoadStage(BaseModel):
    """One constant-load stage used by the smoke and later capacity profiles."""

    model_config = ConfigDict(frozen=True)

    users: int = Field(gt=0, le=100_000)
    spawn_rate: float = Field(gt=0.0, le=100_000.0)
    duration_seconds: int = Field(gt=0, le=86_400)


class PerformanceThreshold(BaseModel):
    """One machine-checkable SLI boundary."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    metric: PerformanceMetric
    operator: ComparisonOperator
    threshold: float = Field(ge=0.0)


class PerformanceProfile(BaseModel):
    """A repeatable load shape and its quality objectives."""

    model_config = ConfigDict(frozen=True)

    version: Literal[1]
    name: str = Field(min_length=1, max_length=120)
    base_url: AnyHttpUrl
    workspace: str = Field(pattern=r"^[A-Za-z0-9-]+$")
    authentication: AuthenticationMode = "none"
    account_pool_size: int = Field(default=16, ge=1, le=10_000)
    token_refresh_after_seconds: int | None = Field(default=None, ge=1, le=3600)
    stages: tuple[LoadStage, ...] = Field(min_length=1)
    thresholds: tuple[PerformanceThreshold, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_threshold_names(self) -> Self:
        names = [threshold.name for threshold in self.thresholds]
        if len(names) != len(set(names)):
            raise ValueError("performance threshold names must be unique")
        return self


class ObservedPerformance(BaseModel):
    """Metrics collected from one completed load run."""

    model_config = ConfigDict(frozen=True)

    total_requests: int = Field(ge=0)
    error_rate: float = Field(ge=0.0, le=1.0)
    p50_response_time_ms: float = Field(default=0.0, ge=0.0)
    p95_response_time_ms: float = Field(ge=0.0)
    p99_response_time_ms: float = Field(ge=0.0)
    requests_per_second: float = Field(default=0.0, ge=0.0)
    duration_seconds: float = Field(default=0.0, ge=0.0)


class ThresholdResult(BaseModel):
    """Evaluation of one threshold against observed metrics."""

    model_config = ConfigDict(frozen=True)

    name: str
    metric: PerformanceMetric
    actual: float
    operator: ComparisonOperator
    threshold: float
    passed: bool


def load_performance_profile(path: Path) -> PerformanceProfile:
    """Load and validate one YAML performance profile."""

    if not path.is_file():
        raise FileNotFoundError(f"performance profile not found: {path}")
    payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("performance profile must contain a YAML mapping")
    return PerformanceProfile.model_validate(payload)


def evaluate_thresholds(
    thresholds: tuple[PerformanceThreshold, ...],
    observed: ObservedPerformance,
) -> tuple[bool, tuple[ThresholdResult, ...]]:
    """Evaluate every objective and keep all results for diagnostics."""

    values = observed.model_dump()
    results: list[ThresholdResult] = []
    for threshold in thresholds:
        actual = float(values[threshold.metric])
        if threshold.operator == "lte":
            passed = actual <= threshold.threshold
        else:
            passed = actual >= threshold.threshold
        results.append(
            ThresholdResult(
                name=threshold.name,
                metric=threshold.metric,
                actual=actual,
                operator=threshold.operator,
                threshold=threshold.threshold,
                passed=passed,
            )
        )
    return all(result.passed for result in results), tuple(results)
