"""Rate-limit tests for the catalog write endpoint."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import pytest
from qa_core.api_errors import classify_response
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings

from tests.api.conftest import attach_json, items_path, unique_client_id


@pytest.mark.api
def test_write_budget_returns_429_with_retry_after(
    owner_auth: AuthClient,
    settings: Settings,
) -> None:
    client_id = unique_client_id("ratelimit")
    headers = {"X-QA-Client-Id": client_id}
    invalid_body = {"name": "no sku", "price_cents": 100}

    for _ in range(settings.rate_limit_write_max):
        accepted = owner_auth.post(
            items_path(),
            json=invalid_body,
            headers=headers,
        )
        assert accepted.status_code == 422

    limited = owner_auth.post(
        items_path(),
        json=invalid_body,
        headers=headers,
    )

    assert limited.status_code == 429
    assert limited.json()["error"] == "rate_limited"
    assert limited.headers.get("Retry-After")
    assert classify_response(limited).category == "environment"
    attach_json(
        "Rate limited response",
        {
            "limit": settings.rate_limit_write_max,
            "status": limited.status_code,
            "retry_after": limited.headers.get("Retry-After"),
            "body": limited.json(),
        },
    )
