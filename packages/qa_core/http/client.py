"""Synchronous HTTP client with bounded retries and structured request logs."""

from __future__ import annotations

import email.utils
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Self

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from qa_core.config.settings import Settings

logger = structlog.get_logger(__name__)

DEFAULT_RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
IDEMPOTENT_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PUT", "TRACE"})


class RetryPolicy(BaseModel):
    """Control retry decisions and delay calculation."""

    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_seconds: float = Field(default=0.25, ge=0.0, le=30.0)
    max_backoff_seconds: float = Field(default=2.0, ge=0.0, le=120.0)
    jitter_ratio: float = Field(default=0.2, ge=0.0, le=1.0)
    retry_status_codes: frozenset[int] = Field(
        default_factory=lambda: DEFAULT_RETRY_STATUS_CODES
    )

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build a retry policy from typed project settings."""

        return cls(
            max_attempts=settings.api_retry_max_attempts,
            backoff_seconds=settings.api_retry_backoff_seconds,
            max_backoff_seconds=settings.api_retry_max_backoff_seconds,
            jitter_ratio=settings.api_retry_jitter_ratio,
        )

    def delay_seconds(
        self,
        attempt: int,
        *,
        retry_after: str | None = None,
        random_value: float = 0.5,
        now: datetime | None = None,
    ) -> float:
        """Return a bounded delay for the next request attempt."""

        if attempt < 1:
            raise ValueError("attempt must be at least 1")

        server_delay = _parse_retry_after(retry_after, now=now)
        if server_delay is not None:
            return min(server_delay, self.max_backoff_seconds)

        exponential_delay = min(
            self.backoff_seconds * (2 ** (attempt - 1)),
            self.max_backoff_seconds,
        )
        jitter_multiplier = (2.0 * random_value) - 1.0
        jitter = exponential_delay * self.jitter_ratio * jitter_multiplier
        delay = max(0.0, min(exponential_delay + jitter, self.max_backoff_seconds))
        return float(delay)


def _parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    if value is None:
        return None

    try:
        seconds = float(value)
    except ValueError:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        return max(0.0, (parsed - current).total_seconds())

    return max(0.0, seconds)


def _safe_request_path(url: str) -> str:
    try:
        return httpx.URL(url).path or "/"
    except httpx.InvalidURL:
        return "<invalid-url>"


class HttpClient:
    """Wrap httpx with project timeouts, retries, and structured logging."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: httpx.Timeout | float = 5.0,
        retry_policy: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep
        self._random_value = random_value
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build a client from the shared typed settings."""

        timeout = httpx.Timeout(
            connect=settings.api_connect_timeout_seconds,
            read=settings.api_read_timeout_seconds,
            write=settings.api_write_timeout_seconds,
            pool=settings.api_pool_timeout_seconds,
        )
        return cls(
            base_url=str(settings.api_base_url),
            timeout=timeout,
            retry_policy=RetryPolicy.from_settings(settings),
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying connection pool."""

        self._client.close()

    def clear_cookies(self) -> None:
        """Remove cookies stored by the underlying httpx client."""

        self._client.cookies.clear()

    def request(
        self,
        method: str,
        url: str,
        *,
        retry: bool | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send one request and retry only when the operation is safe to repeat."""

        normalized_method = method.upper()
        should_retry = (
            normalized_method in IDEMPOTENT_METHODS if retry is None else retry
        )

        for attempt in range(1, self.retry_policy.max_attempts + 1):
            started_at = time.perf_counter()
            try:
                response = self._client.request(normalized_method, url, **kwargs)
            except httpx.TransportError as exc:
                self._log_request(
                    method=normalized_method,
                    path=_safe_request_path(url),
                    attempt=attempt,
                    duration_seconds=time.perf_counter() - started_at,
                    outcome="transport_error",
                    error_type=type(exc).__name__,
                )
                if not should_retry or attempt == self.retry_policy.max_attempts:
                    raise
                self._wait_before_retry(
                    method=normalized_method,
                    path=_safe_request_path(url),
                    attempt=attempt,
                )
                continue

            duration_seconds = time.perf_counter() - started_at
            self._log_request(
                method=normalized_method,
                path=_safe_request_path(url),
                attempt=attempt,
                duration_seconds=duration_seconds,
                outcome="response",
                status_code=response.status_code,
            )

            can_retry_status = (
                should_retry
                and response.status_code in self.retry_policy.retry_status_codes
                and attempt < self.retry_policy.max_attempts
            )
            if not can_retry_status:
                return response

            retry_after = response.headers.get("Retry-After")
            response.close()
            self._wait_before_retry(
                method=normalized_method,
                path=_safe_request_path(url),
                attempt=attempt,
                retry_after=retry_after,
            )

        raise RuntimeError("Retry loop exited without a response.")

    def get(self, url: str, *, retry: bool | None = None, **kwargs: Any) -> httpx.Response:
        """Send a GET request."""

        return self.request("GET", url, retry=retry, **kwargs)

    def post(self, url: str, *, retry: bool | None = None, **kwargs: Any) -> httpx.Response:
        """Send a POST request. Retries are opt-in because POST is not idempotent."""

        return self.request("POST", url, retry=retry, **kwargs)

    def _wait_before_retry(
        self,
        *,
        method: str,
        path: str,
        attempt: int,
        retry_after: str | None = None,
    ) -> None:
        delay = self.retry_policy.delay_seconds(
            attempt,
            retry_after=retry_after,
            random_value=self._random_value(),
        )
        logger.info(
            "http_request_retry",
            method=method,
            path=path,
            attempt=attempt,
            next_attempt=attempt + 1,
            delay_seconds=round(delay, 6),
        )
        self._sleep(delay)

    @staticmethod
    def _log_request(
        *,
        method: str,
        path: str,
        attempt: int,
        duration_seconds: float,
        outcome: str,
        status_code: int | None = None,
        error_type: str | None = None,
    ) -> None:
        logger.info(
            "http_request",
            method=method,
            path=path,
            attempt=attempt,
            duration_ms=round(duration_seconds * 1000, 3),
            outcome=outcome,
            status_code=status_code,
            error_type=error_type,
        )
