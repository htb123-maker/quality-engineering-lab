"""Week 28 stress and spike profile contracts."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from qa_core.performance import load_performance_profile


def _load_capacity_analyzer() -> ModuleType:
    path = Path("scripts/analyze_capacity_results.py")
    spec = importlib.util.spec_from_file_location("analyze_capacity_results", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_stress_profile_ramps_through_multiple_load_stages() -> None:
    profile = load_performance_profile(Path("configs/performance-stress.yaml"))
    users = [stage.users for stage in profile.stages]

    assert profile.name == "week28-stress"
    assert profile.authentication == "password"
    assert profile.workspace == "qa-perf-week28-capacity"
    assert profile.account_pool_size >= max(stage.users for stage in profile.stages)
    assert users == [4, 8, 12, 16, 24]
    assert users == sorted(users)
    assert len(users) >= 5


def test_spike_profile_has_a_short_burst_and_recovery_stage() -> None:
    profile = load_performance_profile(Path("configs/performance-spike.yaml"))
    before, spike, after = profile.stages

    assert profile.name == "week28-spike"
    assert profile.account_pool_size >= spike.users
    assert spike.users >= before.users * 8
    assert spike.duration_seconds < before.duration_seconds
    assert after.users == before.users
    assert after.duration_seconds == before.duration_seconds


def test_capacity_profiles_share_the_isolated_performance_boundary() -> None:
    stress = load_performance_profile(Path("configs/performance-stress.yaml"))
    spike = load_performance_profile(Path("configs/performance-spike.yaml"))

    assert stress.base_url == spike.base_url
    assert stress.workspace == spike.workspace
    assert stress.account_pool_size == spike.account_pool_size
    assert stress.token_refresh_after_seconds == spike.token_refresh_after_seconds
    assert {threshold.metric for threshold in stress.thresholds} == {
        "p95_response_time_ms",
        "error_rate",
        "total_requests",
        "requests_per_second",
    }


def test_stage_analysis_detects_saturation_without_throughput_growth() -> None:
    analyzer = _load_capacity_analyzer()
    stages = [
        SimpleNamespace(
            users=4,
            prometheus_rps_mean=10.0,
            prometheus_p95_mean_ms=10.0,
            prometheus_error_ratio_mean=0.0,
        ),
        SimpleNamespace(
            users=8,
            prometheus_rps_mean=10.5,
            prometheus_p95_mean_ms=20.0,
            prometheus_error_ratio_mean=0.0,
        ),
    ]

    analysis = analyzer._derive_analysis("week28-stress", stages)

    assert analysis["breakpoint_observed"] is True
    assert analysis["breakpoint_stages"] == [8]


def test_spike_analysis_requires_recovery_to_baseline_behavior() -> None:
    analyzer = _load_capacity_analyzer()
    stages = [
        SimpleNamespace(
            users=4,
            prometheus_rps_mean=12.0,
            prometheus_p95_mean_ms=20.0,
            prometheus_p99_mean_ms=30.0,
            prometheus_error_ratio_mean=0.0,
        ),
        SimpleNamespace(
            users=32,
            prometheus_rps_mean=55.0,
            prometheus_p95_mean_ms=80.0,
            prometheus_p99_mean_ms=200.0,
            prometheus_error_ratio_mean=0.01,
        ),
        SimpleNamespace(
            users=4,
            prometheus_rps_mean=11.0,
            prometheus_p95_mean_ms=25.0,
            prometheus_p99_mean_ms=35.0,
            prometheus_error_ratio_mean=0.0,
        ),
    ]

    analysis = analyzer._derive_analysis("week28-spike", stages)

    assert analysis["recovery_ok"] is True
    assert analysis["peak_users"] == 32
