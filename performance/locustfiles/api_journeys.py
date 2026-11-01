"""Read-only Locust journeys for the isolated performance environment."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from locust import FastHttpUser, LoadTestShape, between, events, task
from qa_core.performance import (
    ObservedPerformance,
    evaluate_thresholds,
    load_performance_profile,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = Path(
    os.getenv("QA_PERF_PROFILE", str(ROOT / "configs" / "performance-smoke.yaml"))
)
PROFILE = load_performance_profile(PROFILE_PATH)


class StageShape(LoadTestShape):
    """Execute profile stages sequentially without an implicit final stage."""

    def tick(self) -> tuple[int, float] | None:
        elapsed = self.get_run_time()  # type: ignore[no-untyped-call]
        stage_start = 0
        for stage in PROFILE.stages:
            stage_end = stage_start + stage.duration_seconds
            if elapsed < stage_end:
                return stage.users, stage.spawn_rate
            stage_start = stage_end
        return None


class ReadOnlyApiUser(FastHttpUser):
    """Exercise cheap read paths that are safe to repeat in performance runs."""

    host = str(PROFILE.base_url).rstrip("/")
    wait_time = between(0.2, 0.5)

    def _expect_ok(self, response: object, label: str) -> None:
        status_code = getattr(response, "status_code", None)
        if status_code != 200:
            response.failure(f"{label} returned HTTP {status_code}")  # type: ignore[attr-defined]

    @task(4)
    def browse_catalog(self) -> None:
        """Read the seeded catalog through the cache-aside path."""

        with self.client.get(
            f"/api/v1/workspaces/{PROFILE.workspace}/catalog",
            name="GET catalog",
            catch_response=True,
        ) as response:
            self._expect_ok(response, "catalog")
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    response.failure("catalog response was not JSON")
                else:
                    if payload.get("workspace", {}).get("slug") != PROFILE.workspace:
                        response.failure("catalog workspace did not match the profile")

    @task(2)
    def check_openapi(self) -> None:
        """Confirm the contract endpoint remains responsive during the run."""

        with self.client.get(
            "/openapi.json",
            name="GET openapi",
            catch_response=True,
        ) as response:
            self._expect_ok(response, "openapi")

    @task(1)
    def check_liveness(self) -> None:
        """Exercise the cheapest process-level health endpoint."""

        with self.client.get(
            "/health/live",
            name="GET health live",
            catch_response=True,
        ) as response:
            self._expect_ok(response, "health live")


@events.quitting.add_listener  # type: ignore[untyped-decorator]
def enforce_smoke_thresholds(environment: object, **_kwargs: object) -> None:
    """Set a non-zero Locust exit code when any configured SLI is missed."""

    stats = environment.stats.total  # type: ignore[attr-defined]
    total_requests = int(stats.num_requests)
    observed = ObservedPerformance(
        total_requests=total_requests,
        error_rate=float(stats.fail_ratio),
        p95_response_time_ms=float(stats.get_response_time_percentile(0.95)),
        p99_response_time_ms=float(stats.get_response_time_percentile(0.99)),
    )
    passed, results = evaluate_thresholds(PROFILE.thresholds, observed)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        logging.info(
            "SLO %s %s %s=%s threshold=%s",
            status,
            result.name,
            result.metric,
            result.actual,
            result.threshold,
        )
    if not passed:
        environment.process_exit_code = 1  # type: ignore[attr-defined]
        logging.error(
            "performance smoke missed at least one SLO: profile=%s requests=%s",
            PROFILE.name,
            total_requests,
        )
