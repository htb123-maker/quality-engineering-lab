"""Real monitoring-stack acceptance for the Week 27 Compose profile."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import os

import httpx
import pytest


@pytest.mark.integration
def test_sut_metrics_and_correlation_headers(sut_api_url: str) -> None:
    with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
        probe = client.get(
            "/health/live",
            headers={"X-QA-Run-Id": "week27-integration"},
        )
        metrics = client.get("/metrics")

    assert probe.status_code == 200
    assert probe.headers["X-Request-Id"]
    assert probe.headers["X-Trace-Id"]
    assert metrics.status_code == 200
    assert "qa_sut_http_requests_total" in metrics.text
    assert "qa_sut_http_request_duration_seconds" in metrics.text
    assert 'run_id="week27-integration"' in metrics.text


@pytest.mark.integration
def test_prometheus_scraped_the_sut(sut_api_url: str) -> None:
    prometheus_url = os.getenv("QA_PROMETHEUS_URL", "http://127.0.0.1:29090")
    try:
        response = httpx.get(
            f"{prometheus_url.rstrip('/')}/api/v1/query",
            params={"query": "qa_sut_http_requests_total"},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        pytest.skip(f"Prometheus is not running: {type(exc).__name__}: {exc}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["result"]
