"""Unit tests for performance profiles and objective evaluation."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from qa_core.performance import (
    ObservedPerformance,
    PerformanceProfile,
    PerformanceThreshold,
    evaluate_thresholds,
    load_performance_profile,
)


def test_week25_smoke_profile_loads() -> None:
    profile = load_performance_profile(Path("configs/performance-smoke.yaml"))

    assert profile.name == "week25-isolated-smoke"
    assert profile.workspace == "atlas"
    assert profile.stages[0].users == 4
    assert {target.metric for target in profile.thresholds} == {
        "p95_response_time_ms",
        "error_rate",
        "total_requests",
    }


def test_profile_rejects_duplicate_threshold_names() -> None:
    with pytest.raises(ValidationError, match="threshold names must be unique"):
        PerformanceProfile.model_validate(
            {
                "version": 1,
                "name": "invalid",
                "base_url": "http://127.0.0.1:28000",
                "workspace": "atlas",
                "stages": [{"users": 1, "spawn_rate": 1, "duration_seconds": 1}],
                "thresholds": [
                    {
                        "name": "latency",
                        "metric": "p95_response_time_ms",
                        "operator": "lte",
                        "threshold": 100,
                    },
                    {
                        "name": "latency",
                        "metric": "p99_response_time_ms",
                        "operator": "lte",
                        "threshold": 200,
                    },
                ],
            }
        )


def test_evaluate_thresholds_keeps_all_results() -> None:
    thresholds = (
        PerformanceThreshold(
            name="latency",
            metric="p95_response_time_ms",
            operator="lte",
            threshold=100,
        ),
        PerformanceThreshold(
            name="errors",
            metric="error_rate",
            operator="lte",
            threshold=0.01,
        ),
        PerformanceThreshold(
            name="evidence",
            metric="total_requests",
            operator="gte",
            threshold=20,
        ),
    )
    observed = ObservedPerformance(
        total_requests=10,
        error_rate=0.02,
        p95_response_time_ms=80,
        p99_response_time_ms=120,
    )

    passed, results = evaluate_thresholds(thresholds, observed)

    assert passed is False
    assert [result.passed for result in results] == [True, False, False]
