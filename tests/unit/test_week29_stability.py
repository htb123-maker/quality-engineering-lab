"""Week 29 soak and recovery contracts."""

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest
from qa_core.performance import load_performance_profile


def _load_soak_analyzer() -> ModuleType:
    path = Path("scripts/analyze_soak_results.py")
    spec = importlib.util.spec_from_file_location("analyze_soak_results", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_soak_profile_is_a_long_low_load_run() -> None:
    profile = load_performance_profile(Path("configs/performance-soak.yaml"))
    stage = profile.stages[0]

    assert profile.name == "week29-soak"
    assert profile.authentication == "password"
    assert profile.workspace == "qa-perf-week29-soak"
    assert profile.account_pool_size >= stage.users
    assert stage.users == 8
    assert stage.duration_seconds >= 600
    assert len(profile.stages) == 1


def test_soak_profile_keeps_error_and_latency_guardrails() -> None:
    profile = load_performance_profile(Path("configs/performance-soak.yaml"))
    thresholds = {item.metric: item for item in profile.thresholds}

    assert thresholds["error_rate"].threshold == 0.01
    assert thresholds["p95_response_time_ms"].threshold == 500
    assert thresholds["total_requests"].threshold >= 5000
    assert thresholds["requests_per_second"].threshold >= 10


def test_soak_windows_compute_latency_drift() -> None:
    analyzer = _load_soak_analyzer()
    values = [
        (0.0, 20.0),
        (10.0, 22.0),
        (20.0, 24.0),
        (80.0, 30.0),
        (90.0, 32.0),
        (100.0, 34.0),
    ]

    first = analyzer._window(values, start=0.0, end=20.0)
    last = analyzer._window(values, start=80.0, end=100.0)
    delta = analyzer._delta(first, last)

    assert first["mean"] == 22.0
    assert last["mean"] == 32.0
    assert delta["absolute"] == 10.0
    assert delta["percent"] == pytest.approx(500 / 11)


def test_soak_resource_window_reads_api_samples(tmp_path: Path) -> None:
    analyzer = _load_soak_analyzer()
    path = tmp_path / "resources.csv"
    path.write_text(
        "timestamp,run_id,profile,service,cpu_percent,memory_usage_bytes,"
        "memory_limit_bytes,network_io_bytes,block_io_bytes\n"
        "2026-11-16T16:01:00+00:00,r,p,api,5.0,100,1000,0,0\n"
        "2026-11-16T16:02:00+00:00,r,p,api,7.0,140,1000,0,0\n"
        "2026-11-16T16:02:00+00:00,r,p,postgres,99.0,999,1000,0,0\n",
        encoding="utf-8",
    )
    start = datetime.fromisoformat("2026-11-16T16:00:00+00:00").timestamp()
    end = datetime.fromisoformat("2026-11-16T16:03:00+00:00").timestamp()

    cpu, memory = analyzer._resource_window(path, start=start, end=end)

    assert cpu["mean"] == 6.0
    assert memory["mean"] == 120.0
