"""Real TCP faults for timeout and recovery behavior."""

from __future__ import annotations

import httpx
import pytest
from qa_core.http import HttpClient, RetryPolicy
from qa_core.resilience import ToxiproxyClient
from qa_core.resilience.toxiproxy import latency_toxic
from structlog.testing import capture_logs


@pytest.mark.api
@pytest.mark.fault_injection
def test_disabled_proxy_fails_fast_and_recovers_when_enabled(
    fault_proxy: tuple[ToxiproxyClient, str, str],
) -> None:
    client, proxy_name, proxy_url = fault_proxy

    client.set_proxy_enabled(proxy_name, enabled=False)
    try:
        with httpx.Client(base_url=proxy_url, timeout=0.5) as http:
            try:
                response = http.get("/health/live")
            except httpx.TransportError:
                fault_observed = True
            else:
                fault_observed = response.status_code >= 500
    finally:
        client.set_proxy_enabled(proxy_name, enabled=True)

    # Docker publishes the listener differently by host: Windows returns 502,
    # while Linux resets the connection. Both prove the request did not succeed.
    assert fault_observed

    with httpx.Client(base_url=proxy_url, timeout=1.0) as http:
        response = http.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


@pytest.mark.api
@pytest.mark.fault_injection
def test_read_timeout_retries_are_bounded_and_observable(
    fault_proxy: tuple[ToxiproxyClient, str, str],
) -> None:
    client, proxy_name, proxy_url = fault_proxy
    client.add_toxic(
        proxy_name,
        latency_toxic(latency_ms=300),
    )
    try:
        with capture_logs() as logs, HttpClient(
            base_url=proxy_url,
            timeout=httpx.Timeout(connect=0.5, read=0.05, write=0.5, pool=0.5),
            retry_policy=RetryPolicy(
                max_attempts=2,
                backoff_seconds=0.0,
                max_backoff_seconds=0.0,
                jitter_ratio=0.0,
            ),
        ) as http:
            with pytest.raises(httpx.ReadTimeout):
                http.get("/health/live")
    finally:
        client.remove_toxic(proxy_name, "latency")

    transport_errors = [
        event
        for event in logs
        if event["event"] == "http_request"
        and event["outcome"] == "transport_error"
        and event["error_type"] == "ReadTimeout"
    ]
    assert len(transport_errors) == 2
    assert [event["attempt"] for event in transport_errors] == [1, 2]
