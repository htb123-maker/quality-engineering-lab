"""Unit tests for the shared HTTP client."""

from collections.abc import Callable

import httpx
import pytest
from qa_core.http import HttpClient, RetryPolicy
from structlog.testing import capture_logs

RequestHandler = Callable[[httpx.Request], httpx.Response]


def _client(
    handler: RequestHandler,
    *,
    retry_policy: RetryPolicy | None = None,
    sleeps: list[float] | None = None,
) -> HttpClient:
    recorded_sleeps = sleeps if sleeps is not None else []
    return HttpClient(
        base_url="https://example.test",
        retry_policy=retry_policy or RetryPolicy(),
        transport=httpx.MockTransport(handler),
        sleep=recorded_sleeps.append,
        random_value=lambda: 0.5,
    )


def test_get_uses_base_url_and_returns_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.test/health/live"
        return httpx.Response(200, json={"status": "live"}, request=request)

    with _client(handler) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_retryable_status_honors_retry_after() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                503,
                headers={"Retry-After": "0.5"},
                request=request,
            )
        return httpx.Response(200, request=request)

    policy = RetryPolicy(max_attempts=2, backoff_seconds=10, max_backoff_seconds=2)
    with _client(handler, retry_policy=policy, sleeps=sleeps) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert attempts == 2
    assert sleeps == [0.5]


def test_non_retryable_status_is_returned_immediately() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, request=request)

    with _client(handler) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert attempts == 1


def test_post_retry_is_opt_in() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    policy = RetryPolicy(max_attempts=3, backoff_seconds=0, max_backoff_seconds=0)
    with _client(handler, retry_policy=policy) as client:
        response = client.post("/jobs", json={"name": "example"})

    assert response.status_code == 503
    assert attempts == 1


def test_post_can_opt_in_to_retry() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        status_code = 503 if attempts == 1 else 200
        return httpx.Response(status_code, request=request)

    policy = RetryPolicy(max_attempts=2, backoff_seconds=0, max_backoff_seconds=0)
    with _client(handler, retry_policy=policy, sleeps=sleeps) as client:
        response = client.post("/jobs", retry=True, json={"name": "example"})

    assert response.status_code == 200
    assert attempts == 2
    assert sleeps == [0.0]


def test_transport_error_retries_then_raises() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection failed", request=request)

    policy = RetryPolicy(max_attempts=3, backoff_seconds=0, max_backoff_seconds=0)
    with pytest.raises(httpx.ConnectError), _client(
        handler,
        retry_policy=policy,
        sleeps=sleeps,
    ) as client:
        client.get("/health/live")

    assert attempts == 3
    assert sleeps == [0.0, 0.0]


def test_request_log_contains_safe_operational_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "live"}, request=request)

    with capture_logs() as logs, _client(handler) as client:
        client.get("/health/live", params={"token": "must-not-be-logged"})

    request_events = [event for event in logs if event["event"] == "http_request"]
    assert len(request_events) == 1
    expected_fields = {
        "event": "http_request",
        "method": "GET",
        "path": "/health/live",
        "attempt": 1,
        "outcome": "response",
        "status_code": 200,
        "error_type": None,
    }
    assert expected_fields.items() <= request_events[0].items()
    assert isinstance(request_events[0]["duration_ms"], float)
    assert "must-not-be-logged" not in repr(logs)
