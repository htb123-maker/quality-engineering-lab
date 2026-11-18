"""Analyze Week 28 stress and spike runs by profile stage."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from qa_core.performance import load_performance_profile


@dataclass(frozen=True)
class StageAnalysis:
    """One profile stage aligned with Locust, resource, and Prometheus data."""

    users: int
    duration_seconds: int
    observed_users_median: float
    observed_users_max: int
    requests: int
    failures: int
    locust_rps_mean: float
    locust_rps_max: float
    locust_p95_median_ms: float
    locust_p95_max_ms: float
    locust_p99_max_ms: float
    prometheus_rps_mean: float
    prometheus_p95_mean_ms: float
    prometheus_p99_mean_ms: float
    prometheus_error_ratio_mean: float
    prometheus_avg_response_ms: float
    prometheus_in_progress_mean: float
    api_cpu_percent_mean: float
    postgres_cpu_percent_mean: float
    redis_cpu_percent_mean: float
    postgres_connections_mean: float
    redis_clients_mean: float
    resource_api_cpu_percent_median: float
    resource_api_memory_bytes_max: int
    resource_postgres_cpu_percent_median: float
    resource_redis_cpu_percent_median: float
    little_law_expected_concurrency: float
    little_law_observed_concurrency: float
    little_law_relative_error: float | None


def analyze_profile(
    profile_path: Path,
    run_dir: Path,
    prometheus_url: str,
) -> dict[str, Any]:
    """Analyze one measured run against its declarative profile stages."""

    profile = load_performance_profile(profile_path)
    manifest = _load_json(run_dir / "manifest.json")
    run_start = datetime.fromisoformat(str(manifest["started_at"]))
    history = _locust_history(run_dir / "locust_stats_history.csv")
    resources = _resource_history(run_dir / "resources.csv")

    stages: list[StageAnalysis] = []
    offset = 0
    with httpx.Client(base_url=prometheus_url.rstrip("/"), timeout=10.0) as client:
        for stage in profile.stages:
            start = run_start.timestamp() + offset
            end = start + stage.duration_seconds
            rows = [
                row
                for row in history
                if start <= row["timestamp"] < end
            ]
            resource_rows = [
                row
                for row in resources
                if start <= row["timestamp"] < end
            ]
            prometheus = _prometheus_stage(client, start, end)
            stages.append(
                _stage_analysis(
                    users=stage.users,
                    duration_seconds=stage.duration_seconds,
                    history_rows=rows,
                    resource_rows=resource_rows,
                    prometheus=prometheus,
                )
            )
            offset += stage.duration_seconds

    payload = {
        "schema_version": 1,
        "profile_name": profile.name,
        "profile_path": str(profile_path.resolve()),
        "run_dir": str(run_dir.resolve()),
        "run_id": manifest["run_id"],
        "started_at": manifest["started_at"],
        "finished_at": manifest["finished_at"],
        "stages": [asdict(stage) for stage in stages],
    }
    payload["analysis"] = _derive_analysis(profile.name, stages)
    return payload


def _locust_history(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["Type"] or row["Name"] != "Aggregated":
                continue
            rows.append(
                {
                    "timestamp": float(row["Timestamp"]),
                    "users": int(row["User Count"]),
                    "rps": float(row["Requests/s"]),
                    "p50": _float(row["50%"]),
                    "p95": _float(row["95%"]),
                    "p99": _float(row["99%"]),
                    "requests": int(row["Total Request Count"]),
                    "failures": int(row["Total Failure Count"]),
                    "average_response_ms": float(row["Total Average Response Time"]),
                }
            )
    return rows


def _resource_history(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "timestamp": datetime.fromisoformat(row["timestamp"]).timestamp(),
                    "service": row["service"],
                    "cpu_percent": float(row["cpu_percent"]),
                    "memory_usage_bytes": int(row["memory_usage_bytes"]),
                }
            )
    return rows


def _prometheus_stage(
    client: httpx.Client,
    start: float,
    end: float,
) -> dict[str, float]:
    queries = {
        "rps": "sum(rate(qa_sut_http_requests_total[30s]))",
        "p95_ms": (
            "1000 * histogram_quantile(0.95, sum by (le) "
            "(rate(qa_sut_http_request_duration_seconds_bucket[30s])))"
        ),
        "p99_ms": (
            "1000 * histogram_quantile(0.99, sum by (le) "
            "(rate(qa_sut_http_request_duration_seconds_bucket[30s])))"
        ),
        "error_ratio": (
            "sum(rate(qa_sut_http_requests_total{status=~\"5..\"}[30s])) "
            "/ clamp_min(sum(rate(qa_sut_http_requests_total[30s])), 0.001)"
        ),
        "avg_response_ms": (
            "1000 * sum(rate(qa_sut_http_request_duration_seconds_sum[30s])) "
            "/ clamp_min(sum(rate(qa_sut_http_request_duration_seconds_count[30s])), 0.001)"
        ),
        "in_progress": "qa_sut_http_requests_in_progress",
        "api_cpu_percent": (
            "100 * sum(rate(container_cpu_usage_seconds_total"
            "{container_label_com_docker_compose_service=\"api\"}[30s]))"
        ),
        "postgres_cpu_percent": (
            "100 * sum(rate(container_cpu_usage_seconds_total"
            "{container_label_com_docker_compose_service=\"postgres\"}[30s]))"
        ),
        "redis_cpu_percent": (
            "100 * sum(rate(container_cpu_usage_seconds_total"
            "{container_label_com_docker_compose_service=\"redis\"}[30s]))"
        ),
        "postgres_connections": "sum(pg_stat_database_numbackends{datname=\"qa\"})",
        "redis_clients": "sum(redis_connected_clients)",
    }
    return {
        name: _series_mean(
            _query_range(client, query, start=start, end=end, step=2)
        )
        for name, query in queries.items()
    }


def _query_range(
    client: httpx.Client,
    query: str,
    *,
    start: float,
    end: float,
    step: int,
) -> list[float]:
    response = client.get(
        "/api/v1/query_range",
        params={"query": query, "start": start, "end": end, "step": step},
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("data", {}).get("result", [])
    if not result:
        return []
    return [float(value) for _, value in result[0].get("values", [])]


def _stage_analysis(
    *,
    users: int,
    duration_seconds: int,
    history_rows: list[dict[str, Any]],
    resource_rows: list[dict[str, Any]],
    prometheus: dict[str, float],
) -> StageAnalysis:
    if not history_rows:
        raise ValueError(f"no Locust history samples for {users} users")
    first = history_rows[0]
    last = history_rows[-1]
    requests = max(0, last["requests"] - first["requests"])
    failures = max(0, last["failures"] - first["failures"])
    api_rows = [row for row in resource_rows if row["service"] == "api"]
    postgres_rows = [row for row in resource_rows if row["service"] == "postgres"]
    redis_rows = [row for row in resource_rows if row["service"] == "redis"]
    expected_concurrency = prometheus["rps"] * prometheus["avg_response_ms"] / 1000
    observed_concurrency = prometheus["in_progress"]
    denominator = max(abs(expected_concurrency), 0.001)
    relative_error = (
        abs(expected_concurrency - observed_concurrency) / denominator
        if expected_concurrency > 0
        else None
    )
    return StageAnalysis(
        users=users,
        duration_seconds=duration_seconds,
        observed_users_median=statistics.median(row["users"] for row in history_rows),
        observed_users_max=max(row["users"] for row in history_rows),
        requests=requests,
        failures=failures,
        locust_rps_mean=statistics.mean(row["rps"] for row in history_rows),
        locust_rps_max=max(row["rps"] for row in history_rows),
        locust_p95_median_ms=statistics.median(row["p95"] for row in history_rows),
        locust_p95_max_ms=max(row["p95"] for row in history_rows),
        locust_p99_max_ms=max(row["p99"] for row in history_rows),
        prometheus_rps_mean=prometheus["rps"],
        prometheus_p95_mean_ms=prometheus["p95_ms"],
        prometheus_p99_mean_ms=prometheus["p99_ms"],
        prometheus_error_ratio_mean=prometheus["error_ratio"],
        prometheus_avg_response_ms=prometheus["avg_response_ms"],
        prometheus_in_progress_mean=observed_concurrency,
        api_cpu_percent_mean=prometheus["api_cpu_percent"],
        postgres_cpu_percent_mean=prometheus["postgres_cpu_percent"],
        redis_cpu_percent_mean=prometheus["redis_cpu_percent"],
        postgres_connections_mean=prometheus["postgres_connections"],
        redis_clients_mean=prometheus["redis_clients"],
        resource_api_cpu_percent_median=_median_or_zero(
            row["cpu_percent"] for row in api_rows
        ),
        resource_api_memory_bytes_max=(
            max(row["memory_usage_bytes"] for row in api_rows) if api_rows else 0
        ),
        resource_postgres_cpu_percent_median=_median_or_zero(
            row["cpu_percent"] for row in postgres_rows
        ),
        resource_redis_cpu_percent_median=_median_or_zero(
            row["cpu_percent"] for row in redis_rows
        ),
        little_law_expected_concurrency=expected_concurrency,
        little_law_observed_concurrency=observed_concurrency,
        little_law_relative_error=relative_error,
    )


def _derive_analysis(
    profile_name: str,
    stages: list[StageAnalysis],
) -> dict[str, Any]:
    breakpoint_stages: list[int] = []
    for previous, current in zip(stages, stages[1:], strict=False):
        user_growth = current.users / previous.users - 1
        rps_growth = (
            current.prometheus_rps_mean / previous.prometheus_rps_mean - 1
            if previous.prometheus_rps_mean > 0
            else 0
        )
        p95_growth = (
            current.prometheus_p95_mean_ms / previous.prometheus_p95_mean_ms - 1
            if previous.prometheus_p95_mean_ms > 0
            else 0
        )
        if (
            user_growth >= 0.2
            and rps_growth < 0.1
            and p95_growth > 0.25
        ) or current.prometheus_error_ratio_mean > 0.01:
            breakpoint_stages.append(current.users)

    if profile_name == "week28-spike" and len(stages) >= 3:
        before, spike, recovery = stages[0], stages[1], stages[2]
        recovery_ok = (
            recovery.prometheus_rps_mean >= before.prometheus_rps_mean * 0.8
            and recovery.prometheus_p95_mean_ms
            <= max(before.prometheus_p95_mean_ms * 2, 100)
            and recovery.prometheus_error_ratio_mean <= 0.01
        )
        return {
            "kind": "spike",
            "peak_users": spike.users,
            "peak_rps": spike.prometheus_rps_mean,
            "peak_p95_ms": spike.prometheus_p95_mean_ms,
            "peak_p99_ms": spike.prometheus_p99_mean_ms,
            "peak_error_ratio": spike.prometheus_error_ratio_mean,
            "recovery_rps": recovery.prometheus_rps_mean,
            "recovery_p95_ms": recovery.prometheus_p95_mean_ms,
            "recovery_ok": recovery_ok,
            "breakpoint_stages": breakpoint_stages,
        }

    return {
        "kind": "stress",
        "breakpoint_observed": bool(breakpoint_stages),
        "breakpoint_stages": breakpoint_stages,
        "capacity_lower_bound_users": max(stage.users for stage in stages),
        "highest_stage_rps": stages[-1].prometheus_rps_mean,
        "highest_stage_p95_ms": stages[-1].prometheus_p95_mean_ms,
        "highest_stage_error_ratio": stages[-1].prometheus_error_ratio_mean,
    }


def _series_mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _median_or_zero(values: Any) -> float:
    items = list(values)
    return statistics.median(items) if items else 0.0


def _float(value: str) -> float:
    return 0.0 if value == "N/A" else float(value)


def _load_json(path: Path) -> dict[str, Any]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stress-profile", type=Path, required=True)
    parser.add_argument("--stress-run", type=Path, required=True)
    parser.add_argument("--spike-profile", type=Path, required=True)
    parser.add_argument("--spike-run", type=Path, required=True)
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:29090")
    parser.add_argument(
        "--output",
        type=Path,
        default=root
        / "artifacts"
        / "performance"
        / "week28"
        / "week28-capacity"
        / "capacity-analysis.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "stress": analyze_profile(
            args.stress_profile,
            args.stress_run,
            args.prometheus_url,
        ),
        "spike": analyze_profile(
            args.spike_profile,
            args.spike_run,
            args.prometheus_url,
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Evidence: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
