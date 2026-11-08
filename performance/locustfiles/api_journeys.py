"""Named Locust journeys for anonymous smoke and authenticated load runs."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from locust import FastHttpUser, LoadTestShape, between, events, task
from qa_core.performance import (
    ObservedPerformance,
    PerformanceRuntimeData,
    evaluate_thresholds,
    load_performance_profile,
    load_runtime_data,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = Path(os.getenv("QA_PERF_PROFILE", str(ROOT / "configs" / "performance-smoke.yaml")))
PROFILE = load_performance_profile(PROFILE_PATH)
RUNTIME_DATA_PATH = Path(os.getenv("QA_PERF_DATA_FILE", ""))
RUNTIME_DATA: PerformanceRuntimeData | None
if PROFILE.authentication == "password":
    if not os.getenv("QA_PERF_DATA_FILE"):
        raise RuntimeError("QA_PERF_DATA_FILE is required for authenticated profiles")
    RUNTIME_DATA = load_runtime_data(RUNTIME_DATA_PATH)
else:
    RUNTIME_DATA = None

WORKSPACE = RUNTIME_DATA.workspace_slug if RUNTIME_DATA is not None else PROFILE.workspace
RUN_DIR_VALUE = os.getenv("QA_PERF_RUN_DIR")
RUN_DIR = Path(RUN_DIR_VALUE) if RUN_DIR_VALUE else None
RUN_ID = os.getenv("QA_PERF_RUN_ID", PROFILE.name)
WARMUP_SECONDS = float(os.getenv("QA_PERF_WARMUP_SECONDS", "0"))
SKIP_SLO = os.getenv("QA_PERF_SKIP_SLO") == "1"
IS_WORKER = os.getenv("QA_PERF_WORKER") == "1"
RUN_STARTED_AT = time.monotonic()


class StageShape(LoadTestShape):
    """Execute profile stages, optionally stopping after a warmup boundary."""

    def tick(self) -> tuple[int, float] | None:
        elapsed = self.get_run_time()  # type: ignore[no-untyped-call]
        if WARMUP_SECONDS > 0 and elapsed >= WARMUP_SECONDS:
            return None
        stage_start = 0.0
        for stage in PROFILE.stages:
            stage_end = stage_start + stage.duration_seconds
            if elapsed < stage_end:
                return stage.users, stage.spawn_rate
            stage_start = stage_end
        return None


if RUNTIME_DATA is None:

    class ApiUser(FastHttpUser):
        """Read-only Week 25 smoke user."""

        host = str(PROFILE.base_url).rstrip("/")
        wait_time = between(0.2, 0.5)

        def _expect_ok(self, response: Any, label: str) -> None:
            if response.status_code != 200:
                response.failure(f"{label} returned HTTP {response.status_code}")

        @task(4)
        def browse_catalog(self) -> None:
            """Read the seed workspace catalog through the cache-aside path."""

            with self.client.get(
                f"/api/v1/workspaces/{WORKSPACE}/catalog",
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
                        workspace = payload.get("workspace", {})
                        if workspace.get("slug") != WORKSPACE:
                            response.failure("catalog workspace did not match the profile")

        @task(2)
        def check_openapi(self) -> None:
            """Confirm the contract endpoint remains responsive."""

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

else:
    AUTH_DATA = RUNTIME_DATA

    class ApiUser(FastHttpUser):  # type: ignore[no-redef]
        """Authenticated baseline/load user backed by the isolated data pool."""

        host = str(PROFILE.base_url).rstrip("/")
        wait_time = between(0.2, 0.5)

        def on_start(self) -> None:
            """Log in once and schedule the configured token refresh."""

            self._account_index = 0
            self._access_token = ""
            self._refresh_token = ""
            self._refresh_at = time.monotonic()
            self._headers: dict[str, str] = {}
            self._account_index = id(self) % len(AUTH_DATA.accounts)
            self._login()

        def _login(self) -> None:
            account = AUTH_DATA.accounts[self._account_index]
            with self.client.post(
                "/oauth/token",
                data={
                    "grant_type": "password",
                    "username": account.email,
                    "password": AUTH_DATA.password,
                },
                name="POST login",
                catch_response=True,
            ) as response:
                if response.status_code != 200:
                    response.failure(f"login returned HTTP {response.status_code}")
                    raise RuntimeError("performance login failed")
                self._capture_tokens(response.json())

        def _refresh_if_needed(self) -> None:
            if time.monotonic() < self._refresh_at:
                return
            with self.client.post(
                "/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                name="POST token refresh",
                catch_response=True,
            ) as response:
                if response.status_code != 200:
                    response.failure(f"token refresh returned HTTP {response.status_code}")
                    self._login()
                    return
                self._capture_tokens(response.json())

        def _capture_tokens(self, payload: dict[str, Any]) -> None:
            access_token = payload.get("access_token")
            refresh_token = payload.get("refresh_token")
            expires_in = payload.get("expires_in", 300)
            if not isinstance(access_token, str) or not isinstance(refresh_token, str):
                raise RuntimeError("token response did not contain token strings")
            if not isinstance(expires_in, int) or expires_in <= 0:
                raise RuntimeError("token response did not contain a positive expiry")
            self._access_token = access_token
            self._refresh_token = refresh_token
            self._headers = {"Authorization": f"Bearer {access_token}"}
            configured_refresh = PROFILE.token_refresh_after_seconds or expires_in
            refresh_after = max(1, min(configured_refresh, expires_in - 5))
            self._refresh_at = time.monotonic() + refresh_after

        def _expect_ok(self, response: Any, label: str) -> None:
            if response.status_code != 200:
                response.failure(f"{label} returned HTTP {response.status_code}")

        @task(4)
        def browse_catalog(self) -> None:
            """Read the isolated workspace catalog."""

            self._refresh_if_needed()
            with self.client.get(
                f"/api/v1/workspaces/{WORKSPACE}/catalog",
                headers=self._headers,
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
                        workspace = payload.get("workspace", {})
                        if workspace.get("slug") != WORKSPACE:
                            response.failure("catalog workspace did not match the data pool")

        @task(2)
        def current_user(self) -> None:
            """Read the authenticated identity and workspace."""

            self._refresh_if_needed()
            with self.client.get(
                "/api/v1/auth/me",
                headers=self._headers,
                name="GET auth me",
                catch_response=True,
            ) as response:
                self._expect_ok(response, "auth me")
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError:
                        response.failure("auth response was not JSON")
                    else:
                        if payload.get("workspace_slug") != WORKSPACE:
                            response.failure("auth workspace did not match the data pool")

        @task(1)
        def check_openapi(self) -> None:
            """Confirm the contract endpoint remains responsive."""

            self._refresh_if_needed()
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


@events.test_start.add_listener  # type: ignore[untyped-decorator]
def mark_test_start(environment: object, **_kwargs: object) -> None:
    """Reset the wall-clock reference for the result manifest."""

    del environment
    global RUN_STARTED_AT
    RUN_STARTED_AT = time.monotonic()


@events.quitting.add_listener  # type: ignore[untyped-decorator]
def enforce_thresholds(environment: object, **_kwargs: object) -> None:
    """Persist the observed metrics and fail the process when any SLO is missed."""

    if IS_WORKER:
        return
    stats = environment.stats.total  # type: ignore[attr-defined]
    duration = max(time.monotonic() - RUN_STARTED_AT, 0.001)
    total_requests = int(stats.num_requests)
    observed = ObservedPerformance(
        total_requests=total_requests,
        error_rate=float(stats.fail_ratio),
        p50_response_time_ms=float(stats.get_response_time_percentile(0.5)),
        p95_response_time_ms=float(stats.get_response_time_percentile(0.95)),
        p99_response_time_ms=float(stats.get_response_time_percentile(0.99)),
        requests_per_second=total_requests / duration,
        duration_seconds=duration,
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
    if RUN_DIR is not None:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "profile": PROFILE.model_dump(mode="json"),
            "profile_path": str(PROFILE_PATH),
            "workspace": WORKSPACE,
            "observed": observed.model_dump(mode="json"),
            "thresholds": [result.model_dump(mode="json") for result in results],
            "slo_passed": passed,
            "skipped_slo": SKIP_SLO,
        }
        (RUN_DIR / "result.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if not passed and not SKIP_SLO:
        environment.process_exit_code = 1  # type: ignore[attr-defined]
        logging.error(
            "performance run missed at least one SLO: profile=%s requests=%s",
            PROFILE.name,
            total_requests,
        )
