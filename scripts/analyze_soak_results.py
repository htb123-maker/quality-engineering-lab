"""Analyze a Week 29 soak run for latency and resource drift."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from qa_core.performance import load_performance_profile

SOAK_QUERIES = {
    "rps": "sum(rate(qa_sut_http_requests_total[1m]))",
    "p95_ms": (
        "1000 * histogram_quantile(0.95, sum by (le) "
        "(rate(qa_sut_http_request_duration_seconds_bucket[1m])))"
    ),
    "p99_ms": (
        "1000 * histogram_quantile(0.99, sum by (le) "
        "(rate(qa_sut_http_request_duration_seconds_bucket[1m])))"
    ),
    "error_ratio": (
        "(sum(rate(qa_sut_http_requests_total{status=~\"5..\"}[1m])) or vector(0)) "
        "/ clamp_min(sum(rate(qa_sut_http_requests_total[1m])), 0.001)"
    ),
    "postgres_connections": "sum(pg_stat_database_numbackends{datname=\"qa\"})",
    "postgres_budget_capacity": "max(qa_sut_postgres_connection_budget_capacity)",
    "postgres_budget_active": "max(qa_sut_postgres_connection_budget_active)",
    "postgres_budget_peak": "max(qa_sut_postgres_connection_budget_peak)",
    "redis_memory_bytes": "sum(redis_memory_used_bytes)",
    "redis_evictions": "sum(increase(redis_evicted_keys_total[1m]))",
    "redis_hit_ratio": (
        "sum(rate(redis_keyspace_hits_total[1m])) "
        "/ clamp_min(sum(rate(redis_keyspace_hits_total[1m])) "
        "+ sum(rate(redis_keyspace_misses_total[1m])), 0.001)"
    ),
    "postgres_wal_bytes": "sum(increase(pg_stat_wal_bytes[1m]))",
}


def _query_series(
    client: httpx.Client,
    query: str,
    *,
    start: float,
    end: float,
    step: int,
) -> list[tuple[float, float]]:
    response = client.get(
        "/api/v1/query_range",
        params={"query": query, "start": start, "end": end, "step": step},
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("data", {}).get("result", [])
    if not result:
        return []
    return [(float(timestamp), float(value)) for timestamp, value in result[0]["values"]]


def _window(
    values: list[tuple[float, float]],
    *,
    start: float,
    end: float,
) -> dict[str, float | int | None]:
    selected = [value for timestamp, value in values if start <= timestamp <= end]
    if not selected:
        return {"count": 0, "mean": None, "min": None, "max": None}
    return {
        "count": len(selected),
        "mean": statistics.mean(selected),
        "min": min(selected),
        "max": max(selected),
    }


def _delta(
    first: dict[str, float | int | None],
    last: dict[str, float | int | None],
) -> dict[str, float | None]:
    first_mean = first["mean"]
    last_mean = last["mean"]
    if first_mean is None or last_mean is None:
        return {"absolute": None, "percent": None}
    absolute = float(last_mean) - float(first_mean)
    percent = None if float(first_mean) == 0 else absolute / float(first_mean) * 100
    return {"absolute": absolute, "percent": percent}


def _resource_window(
    path: Path,
    *,
    start: float,
    end: float,
) -> tuple[dict[str, float | int | None], dict[str, float | int | None]]:
    cpu_values: list[float] = []
    memory_values: list[float] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["service"] != "api":
                continue
            timestamp = datetime.fromisoformat(row["timestamp"]).timestamp()
            if start <= timestamp <= end:
                cpu_values.append(float(row["cpu_percent"]))
                memory_values.append(float(row["memory_usage_bytes"]))
    return _values_summary(cpu_values), _values_summary(memory_values)


def _values_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "min": min(values),
        "max": max(values),
    }


def analyze(
    profile_path: Path,
    run_dir: Path,
    prometheus_url: str,
) -> dict[str, Any]:
    profile = load_performance_profile(profile_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    run_start = datetime.fromisoformat(str(manifest["started_at"]))
    run_end = datetime.fromisoformat(str(manifest["finished_at"]))
    duration = max((run_end - run_start).total_seconds(), 1)
    window_seconds = max(duration * 0.2, 30)
    start = run_start.timestamp()
    end = run_end.timestamp()
    first_end = start + window_seconds
    last_start = end - window_seconds
    step = max(5, int(duration / 60))

    metrics: dict[str, Any] = {}
    with httpx.Client(base_url=prometheus_url.rstrip("/"), timeout=15.0) as client:
        for name, query in SOAK_QUERIES.items():
            values = _query_series(
                client,
                query,
                start=start,
                end=end,
                step=step,
            )
            first = _window(values, start=start, end=first_end)
            last = _window(values, start=last_start, end=end)
            metrics[name] = {
                "first_window": first,
                "last_window": last,
                "delta": _delta(first, last),
            }

    resource_path = run_dir / "resources.csv"
    resource_first_cpu, resource_first_memory = _resource_window(
        resource_path,
        start=start,
        end=first_end,
    )
    resource_last_cpu, resource_last_memory = _resource_window(
        resource_path,
        start=last_start,
        end=end,
    )
    metrics["api_cpu_percent"] = {
        "first_window": resource_first_cpu,
        "last_window": resource_last_cpu,
        "delta": _delta(resource_first_cpu, resource_last_cpu),
    }
    metrics["api_memory_bytes"] = {
        "first_window": resource_first_memory,
        "last_window": resource_last_memory,
        "delta": _delta(resource_first_memory, resource_last_memory),
    }

    first_p95 = metrics["p95_ms"]["first_window"]["mean"]
    last_p95 = metrics["p95_ms"]["last_window"]["mean"]
    p95_delta = metrics["p95_ms"]["delta"]["percent"]
    error_ratio = metrics["error_ratio"]["last_window"]["mean"]
    memory_delta = metrics["api_memory_bytes"]["delta"]["percent"]
    checks = {
        "error_rate_within_guardrail": error_ratio is not None and error_ratio <= 0.01,
        "latency_has_samples": last_p95 is not None,
        "latency_drift_below_50_percent": (
            p95_delta is None or abs(p95_delta) <= 50
        ),
        "api_memory_drift_below_20_percent": (
            memory_delta is None or abs(memory_delta) <= 20
        ),
        "no_redis_evictions": (
            metrics["redis_evictions"]["last_window"]["max"] in (None, 0)
        ),
    }
    return {
        "schema_version": 1,
        "profile_name": profile.name,
        "run_id": manifest["run_id"],
        "started_at": manifest["started_at"],
        "finished_at": manifest["finished_at"],
        "duration_seconds": duration,
        "first_window_seconds": window_seconds,
        "last_window_seconds": window_seconds,
        "metrics": metrics,
        "checks": checks,
        "passed": all(checks.values()),
        "p95_first": first_p95,
        "p95_last": last_p95,
    }


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:29090")
    parser.add_argument(
        "--output",
        type=Path,
        default=root
        / "artifacts"
        / "performance"
        / "week29"
        / "week29-soak"
        / "soak-analysis.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = analyze(args.profile, args.run, args.prometheus_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Evidence: {args.output.resolve()}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
