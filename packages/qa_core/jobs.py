"""Poll the SUT background job API without fixed sleeps.

Week 10 moves work out of the request that asked for it, so a test can no
longer read the result from the same response. Waiting is therefore a bounded
poll against a deadline: the helper returns as soon as the job reaches a final
state and fails loudly with the last observed state when time runs out.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Self

import httpx

from qa_core.auth import AuthClient
from qa_core.cache import open_redis

DEFAULT_WAIT_SECONDS = 15.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.05
FINAL_STATES = ("succeeded", "failed")


def cache_refresh_path(workspace_slug: str) -> str:
    """Return the asynchronous cache refresh path of one workspace."""

    return f"/api/v1/workspaces/{workspace_slug}/catalog/cache/refresh"


def job_path(job_id: str) -> str:
    """Return the path of one background job."""

    return f"/api/v1/jobs/{job_id}"


def queue_stats_path() -> str:
    """Return the path of the background queue statistics."""

    return "/api/v1/jobs"


def job_record_key(job_id: str) -> str:
    """Return the Redis key that stores one job record."""

    return f"job:{job_id}"


def read_job_record(redis_url: str, job_id: str) -> dict[str, Any] | None:
    """Read a job record straight from Redis.

    The API scopes job reads to the workspace that queued them, so a test that
    deliberately deletes that workspace checks the worker's outcome here.
    """

    client = open_redis(redis_url)
    try:
        raw = client.get(job_record_key(job_id))
    finally:
        client.close()
    if raw is None:
        return None
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def wait_for_final_record(
    redis_url: str,
    job_id: str,
    *,
    timeout: float = DEFAULT_WAIT_SECONDS,
    interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any] | None:
    """Poll the stored job record until it reaches a final state."""

    deadline = time.monotonic() + max(timeout, 0.0)
    record = read_job_record(redis_url, job_id)
    while record is not None and record.get("status") not in FINAL_STATES:
        if time.monotonic() >= deadline:
            return record
        time.sleep(interval)
        record = read_job_record(redis_url, job_id)
    return record


class JobTimeout(TimeoutError):
    """Raised when a job does not reach a final state before the deadline."""

    def __init__(self, job_id: str, last_status: str, waited_seconds: float) -> None:
        super().__init__(
            f"Job {job_id} was still '{last_status}' after "
            f"{waited_seconds:.2f}s"
        )
        self.job_id = job_id
        self.last_status = last_status
        self.waited_seconds = waited_seconds


@dataclass(frozen=True)
class JobAccepted:
    """The 202 answer that acknowledges a queued job."""

    job_id: str
    type: str
    workspace_slug: str
    status: str
    queued_at: str
    location: str


@dataclass(frozen=True)
class JobSnapshot:
    """One job record as reported by the SUT."""

    job_id: str
    type: str
    status: str
    workspace_slug: str
    queued_at: str
    started_at: str | None
    finished_at: str | None
    result: dict[str, Any] | None
    error: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        """Validate and copy one API payload."""

        raw_result = payload.get("result")
        return cls(
            job_id=str(payload["job_id"]),
            type=str(payload["type"]),
            status=str(payload["status"]),
            workspace_slug=str(payload["workspace_slug"]),
            queued_at=str(payload["queued_at"]),
            started_at=_optional_text(payload.get("started_at")),
            finished_at=_optional_text(payload.get("finished_at")),
            result=raw_result if isinstance(raw_result, dict) else None,
            error=_optional_text(payload.get("error")),
        )

    @property
    def finished(self) -> bool:
        """Return whether the job stopped running."""

        return self.status in FINAL_STATES

    @property
    def succeeded(self) -> bool:
        """Return whether the job completed without an error."""

        return self.status == "succeeded"


@dataclass(frozen=True)
class QueueStats:
    """Queue depth plus the counters that prove a worker ran."""

    queued: int
    delayed: int
    processed: int
    failed: int
    worker_enabled: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        """Validate and copy one API payload."""

        return cls(
            queued=int(payload["queued"]),
            delayed=int(payload["delayed"]),
            processed=int(payload["processed"]),
            failed=int(payload["failed"]),
            worker_enabled=bool(payload["worker_enabled"]),
        )


class JobClient:
    """Queue jobs and poll them through an authenticated session."""

    def __init__(
        self,
        auth: AuthClient,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._auth = auth
        self._poll_interval = poll_interval

    @classmethod
    def from_auth(cls, auth: AuthClient) -> Self:
        """Bind a job client to an existing authenticated session."""

        return cls(auth)

    def refresh_catalog_cache(
        self,
        workspace_slug: str,
        *,
        delay_seconds: float = 0.0,
        ttl_seconds: int | None = None,
        client_id: str | None = None,
    ) -> JobAccepted:
        """Queue an asynchronous catalog cache refresh."""

        headers: dict[str, str] = {}
        if client_id is not None:
            headers["X-QA-Client-Id"] = client_id
        body: dict[str, Any] = {"delay_seconds": delay_seconds}
        if ttl_seconds is not None:
            body["ttl_seconds"] = ttl_seconds
        response = self._auth.post(
            cache_refresh_path(workspace_slug),
            json=body,
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
        return JobAccepted(
            job_id=str(payload["job_id"]),
            type=str(payload["type"]),
            workspace_slug=str(payload["workspace_slug"]),
            status=str(payload["status"]),
            queued_at=str(payload["queued_at"]),
            location=response.headers.get("Location", ""),
        )

    def queue_stats(self) -> QueueStats:
        """Read queue depth and worker counters."""

        response = self._auth.get(queue_stats_path())
        response.raise_for_status()
        return QueueStats.from_payload(response.json())

    def get(self, job_id: str) -> JobSnapshot:
        """Read one job record."""

        response = self._auth.get(job_path(job_id))
        response.raise_for_status()
        return JobSnapshot.from_payload(response.json())

    def wait(
        self,
        job_id: str,
        *,
        timeout: float = DEFAULT_WAIT_SECONDS,
        states: Sequence[str] = FINAL_STATES,
    ) -> JobSnapshot:
        """Poll until the job reaches one of ``states`` or the deadline passes."""

        deadline = time.monotonic() + max(timeout, 0.0)
        snapshot = self.get(job_id)
        while snapshot.status not in states:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JobTimeout(job_id, snapshot.status, timeout)
            time.sleep(min(self._poll_interval, remaining))
            snapshot = self.get(job_id)
        return snapshot


def _optional_text(value: object) -> str | None:
    """Return ``str(value)`` for real values and ``None`` otherwise."""

    if value is None:
        return None
    text = str(value)
    return text or None


def wait_for_http_status(
    client: httpx.Client,
    url: str,
    *,
    expected: int,
    timeout: float = DEFAULT_WAIT_SECONDS,
    interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    **kwargs: Any,
) -> httpx.Response:
    """GET ``url`` until it answers ``expected``, or raise the last response.

    Cache expiry is a time-based behavior, so a test that waits for a key to
    vanish uses this bounded poll instead of a fixed sleep.
    """

    deadline = time.monotonic() + max(timeout, 0.0)
    response = client.get(url, **kwargs)
    while response.status_code != expected:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return response
        time.sleep(min(interval, remaining))
        response = client.get(url, **kwargs)
    return response
