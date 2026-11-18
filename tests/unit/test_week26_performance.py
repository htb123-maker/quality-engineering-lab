"""Week 26 performance profile, data pool, result, and resource contracts."""

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from qa_core.performance import (
    ObservedPerformance,
    compare_observations,
    load_env_file,
    load_performance_profile,
    normalize_run_id,
    parse_io_pair,
    parse_percent,
    parse_size,
    performance_workspace_slug,
    summarize_observations,
    summarize_resource_csvs,
)


def _load_performance_runner() -> ModuleType:
    path = Path("scripts/run_performance_profile.py")
    spec = importlib.util.spec_from_file_location("run_performance_profile", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failed_locust_log_tail_tolerates_windows_encoding(tmp_path: Path) -> None:
    path = tmp_path / "locust.log"
    path.write_bytes(b"first line\nDLL load failed: \xd3\xa6\xd3\xc3\n")

    tail = _load_performance_runner()._read_log_tail(path)

    assert "first line" in tail
    assert "DLL load failed" in tail
    assert "\ufffd" in tail


def test_locust_environment_uses_windows_pure_python_fallback() -> None:
    runner = _load_performance_runner()

    assert runner._locust_environment({}, platform="win32") == {
        "PURE_PYTHON": "1",
        "QA_PERF_STUB_FASTHTTP": "1",
        "QA_PERF_FAST_HTTP": "0",
    }
    assert runner._locust_environment({"PURE_PYTHON": "0"}, platform="win32") == {
        "PURE_PYTHON": "0",
        "QA_PERF_STUB_FASTHTTP": "1",
        "QA_PERF_FAST_HTTP": "0",
    }
    assert runner._locust_environment({}, platform="linux") == {}


def test_windows_locust_python_path_includes_compatibility_shim(tmp_path: Path) -> None:
    runner = _load_performance_runner()
    path = runner._locust_python_path(
        tmp_path,
        {"QA_PERF_STUB_FASTHTTP": "1"},
    )

    assert path.split(";")[:3] == [
        str(tmp_path / "performance" / "compat"),
        str(tmp_path / "packages"),
        str(tmp_path),
    ]


def test_command_output_accepts_an_explicit_environment(tmp_path: Path) -> None:
    output = _load_performance_runner()._command_output(
        [
            sys.executable,
            "-c",
            "import os; print(os.getenv('PURE_PYTHON', 'missing'))",
        ],
        tmp_path,
        environment={"PURE_PYTHON": "1"},
    )

    assert output == "1"


def test_authenticated_locust_requests_keep_the_run_id_header() -> None:
    tree = ast.parse(
        Path("performance/locustfiles/api_journeys.py").read_text(encoding="utf-8")
    )
    api_user_classes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "ApiUser"
    ]
    authenticated_user = api_user_classes[-1]
    client_calls = [
        node
        for node in ast.walk(authenticated_user)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"get", "post"}
        and "self.client" in ast.unparse(node.func)
    ]

    assert client_calls
    assert all("X-QA-Run-Id" in ast.unparse(call) for call in client_calls)


def test_week26_profiles_only_change_load_shape() -> None:
    baseline = load_performance_profile(Path("configs/performance-baseline.yaml"))
    load = load_performance_profile(Path("configs/performance-load.yaml"))

    assert baseline.authentication == "password"
    assert baseline.workspace == load.workspace
    assert baseline.account_pool_size == load.account_pool_size
    assert baseline.token_refresh_after_seconds == load.token_refresh_after_seconds
    assert baseline.thresholds[0].metric == "p50_response_time_ms"
    assert baseline.stages[0].users == 4
    assert load.stages[0].users == 8
    assert baseline.stages[0].duration_seconds == load.stages[0].duration_seconds


def test_median_summary_and_comparison() -> None:
    observations = (
        ObservedPerformance(
            total_requests=100,
            error_rate=0.0,
            p50_response_time_ms=10,
            p95_response_time_ms=20,
            p99_response_time_ms=30,
            requests_per_second=2.0,
            duration_seconds=50,
        ),
        ObservedPerformance(
            total_requests=120,
            error_rate=0.01,
            p50_response_time_ms=20,
            p95_response_time_ms=30,
            p99_response_time_ms=40,
            requests_per_second=2.4,
            duration_seconds=50,
        ),
        ObservedPerformance(
            total_requests=140,
            error_rate=0.02,
            p50_response_time_ms=30,
            p95_response_time_ms=40,
            p99_response_time_ms=50,
            requests_per_second=2.8,
            duration_seconds=50,
        ),
    )

    summary = summarize_observations(observations)
    comparison = compare_observations(summary, observations[2])

    assert summary.total_requests == 120
    assert summary.p95_response_time_ms == 30
    assert comparison["p95_response_time_ms"]["baseline"] == 30
    assert comparison["p95_response_time_ms"]["percent_delta"] == pytest.approx(100 / 3)


def test_performance_workspace_is_deterministic_and_safe() -> None:
    assert normalize_run_id(" Week 26 / Local ") == "week-26-local"
    assert performance_workspace_slug("Week 26 Local") == "qa-perf-week-26-local"


def test_runtime_env_file_parser_ignores_comments(tmp_path: Path) -> None:
    path = tmp_path / ".env.performance"
    path.write_text(
        "# local only\nQA_API_PORT=28000\nQA_POSTGRES_DSN=postgresql://qa:qa@db/qa\n",
        encoding="utf-8",
    )

    values = load_env_file(path)

    assert values["QA_API_PORT"] == "28000"
    assert values["QA_POSTGRES_DSN"].startswith("postgresql://")


def test_docker_resource_parsers() -> None:
    assert parse_size("1.5MiB") == 1_572_864
    assert parse_size("1e+03kB") == 1_000_000
    assert parse_percent("12.5%") == 12.5
    assert parse_io_pair("1kB / 2kB") == 3_000


def test_resource_csv_summary_uses_medians(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    header = (
        "timestamp,run_id,profile,service,cpu_percent,memory_usage_bytes,"
        "memory_limit_bytes,network_io_bytes,block_io_bytes\n"
    )
    first.write_text(
        header + "t,r,p,api,1,100,1000,10,20\n" + "t,r,p,postgres,3,300,1000,30,40\n",
        encoding="utf-8",
    )
    second.write_text(
        header + "t,r,p,api,5,300,1000,30,40\n" + "t,r,p,postgres,7,500,1000,50,60\n",
        encoding="utf-8",
    )

    summary = summarize_resource_csvs((first, second))

    assert summary["api"]["cpu_percent"] == 3
    assert summary["postgres"]["memory_usage_bytes"] == 400
