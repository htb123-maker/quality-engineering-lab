"""Verify the Week 27 Prometheus, Grafana, Tempo, and correlation path."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class CheckResult:
    """One observability readiness result."""

    name: str
    passed: bool
    detail: str
    status: str


def _result(
    name: str,
    passed: bool,
    detail: str,
    *,
    blocked: bool = False,
) -> CheckResult:
    status = "PASS" if passed else ("BLOCKED" if blocked else "FAILED")
    return CheckResult(name=name, passed=passed, detail=detail, status=status)


def _wait_for(
    client: httpx.Client,
    path: str,
    *,
    deadline: float,
) -> httpx.Response | None:
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = client.get(path)
            if response.status_code < 500:
                return response
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(1)
    if last_error is not None:
        return None
    return None


def verify(args: argparse.Namespace) -> list[CheckResult]:
    """Run the real observability checks against localhost."""

    results: list[CheckResult] = []
    deadline = time.monotonic() + max(args.wait_seconds, 1)
    with httpx.Client(timeout=5.0):
        api = httpx.Client(base_url=args.api_base_url.rstrip("/"), timeout=5.0)
        try:
            probe = api.get(
                "/health/live",
                headers={"X-QA-Run-Id": "week27-monitor-probe"},
            )
            trace_id = probe.headers.get("X-Trace-Id", "")
            request_id = probe.headers.get("X-Request-Id", "")
            results.append(
                _result(
                    "API trace headers",
                    probe.status_code == 200 and bool(trace_id) and bool(request_id),
                    (
                        f"status={probe.status_code}, trace_id={trace_id or '<missing>'}, "
                        f"request_id={request_id or '<missing>'}"
                    ),
                )
            )

            metrics = api.get("/metrics")
            metrics_text = metrics.text if metrics.status_code == 200 else ""
            expected_metrics = {
                "qa_sut_http_requests_total",
                "qa_sut_http_request_duration_seconds",
                'qa_sut_last_request_run_info{run_id="week27-monitor-probe"}',
            }
            missing = sorted(
                metric for metric in expected_metrics if metric not in metrics_text
            )
            results.append(
                _result(
                    "API Prometheus metrics",
                    metrics.status_code == 200 and not missing,
                    f"status={metrics.status_code}, missing={missing}",
                )
            )
        finally:
            api.close()

        prometheus = httpx.Client(
            base_url=args.prometheus_url.rstrip("/"),
            timeout=5.0,
        )
        try:
            targets_response = _wait_for(
                prometheus,
                "/api/v1/targets?state=active",
                deadline=deadline,
            )
            targets: dict[str, str] = {}
            if targets_response is not None and targets_response.status_code == 200:
                payload = targets_response.json()
                for target in payload.get("data", {}).get("activeTargets", []):
                    job = str(target.get("labels", {}).get("job", ""))
                    targets[job] = str(target.get("health", ""))
            required_jobs = {"sut-api", "postgres", "redis", "cadvisor"}
            unhealthy = {
                job: targets.get(job, "missing")
                for job in sorted(required_jobs)
                if targets.get(job) != "up"
            }
            results.append(
                _result(
                    "Prometheus scrape targets",
                    not unhealthy,
                    f"targets={targets}, unhealthy={unhealthy}",
                )
            )
        finally:
            prometheus.close()

        grafana = httpx.Client(base_url=args.grafana_url.rstrip("/"), timeout=5.0)
        try:
            health = _wait_for(grafana, "/api/health", deadline=deadline)
            results.append(
                _result(
                    "Grafana health",
                    health is not None and health.status_code == 200,
                    (
                        health.text
                        if health is not None
                        else "Grafana did not answer before the deadline"
                    ),
                    blocked=health is None,
                )
            )

            dashboard = _wait_for(
                grafana,
                "/api/search?query=Week%2027",
                deadline=deadline,
            )
            dashboard_payload = (
                dashboard.json()
                if dashboard is not None and dashboard.status_code == 200
                else []
            )
            uids = {entry.get("uid") for entry in dashboard_payload}
            results.append(
                _result(
                    "Grafana dashboard provisioning",
                    "week27-sut-overview" in uids,
                    f"dashboard_uids={sorted(uid for uid in uids if uid)}",
                )
            )
        finally:
            grafana.close()

        tempo = httpx.Client(base_url=args.tempo_url.rstrip("/"), timeout=5.0)
        try:
            ready = _wait_for(tempo, "/ready", deadline=deadline)
            results.append(
                _result(
                    "Tempo readiness",
                    ready is not None and ready.status_code == 200,
                    ready.text if ready is not None else "Tempo did not answer",
                    blocked=ready is None,
                )
            )

            if trace_id:
                time.sleep(6)
                trace_response = httpx.get(
                    f"{args.tempo_url.rstrip('/')}/api/traces/{trace_id}",
                    timeout=5.0,
                )
                results.append(
                    _result(
                        "Tempo trace retrieval",
                        trace_response.status_code == 200,
                        (
                            f"trace_id={trace_id}, "
                            f"status={trace_response.status_code}, "
                            f"bytes={len(trace_response.content)}"
                        ),
                    )
                )
        finally:
            tempo.close()

    return results


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:28000")
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:29090")
    parser.add_argument("--grafana-url", default="http://127.0.0.1:23000")
    parser.add_argument("--tempo-url", default="http://127.0.0.1:23200")
    parser.add_argument("--wait-seconds", type=int, default=60)
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "artifacts" / "performance" / "week27" / "observability.json",
    )
    return parser.parse_args()


def main() -> int:
    """Run checks, persist evidence, and return a process exit code."""

    args = parse_args()
    results = verify(args)
    passed = all(result.passed for result in results)
    payload = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "passed": passed,
        "checks": [asdict(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for result in results:
        print(f"{result.status} {result.name}: {result.detail}")
    print(f"Observability ready: {passed}")
    print(f"Evidence: {args.output.resolve()}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
