"""Rate-limit tests for the catalog write endpoint."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import math

import pytest
from qa_core.api_errors import classify_response
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.resource_pools import NamespaceLease

from tests.api.conftest import attach_json, items_path, unique_client_id


@pytest.mark.api
def test_write_budget_returns_429_with_retry_after(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    client_id = unique_client_id("ratelimit")
    headers = {"X-QA-Client-Id": client_id}
    invalid_body = {"name": "no sku", "price_cents": 100}

    for _ in range(settings.rate_limit_write_max):
        accepted = owner_auth.post(
            items_path(namespace.slug),
            json=invalid_body,
            headers=headers,
        )
        assert accepted.status_code == 422

    limited = owner_auth.post(
        items_path(namespace.slug),
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


def _exhaust_budget(
    auth: AuthClient,
    namespace: NamespaceLease,
    settings: Settings,
    client_id: str,
) -> None:
    headers = {"X-QA-Client-Id": client_id}
    invalid_body = {"name": "no sku", "price_cents": 100}
    for _ in range(settings.rate_limit_write_max):
        response = auth.post(
            items_path(namespace.slug),
            json=invalid_body,
            headers=headers,
        )
        assert response.status_code == 422


@pytest.mark.api
def test_budget_is_not_shared_between_clients(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    exhausted_client = unique_client_id("isolated")
    _exhaust_budget(owner_auth, namespace, settings, exhausted_client)

    blocked = owner_auth.post(
        items_path(namespace.slug),
        json={"name": "no sku", "price_cents": 100},
        headers={"X-QA-Client-Id": exhausted_client},
    )
    fresh = owner_auth.post(
        items_path(namespace.slug),
        json={"name": "no sku", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id("fresh")},
    )

    assert blocked.status_code == 429
    assert fresh.status_code == 422
    attach_json(
        "Per-client budget",
        {"blocked": blocked.status_code, "fresh_client": fresh.status_code},
    )


@pytest.mark.api
def test_retry_after_stays_within_the_window(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    client_id = unique_client_id("retry-after")
    _exhaust_budget(owner_auth, namespace, settings, client_id)

    limited = owner_auth.post(
        items_path(namespace.slug),
        json={"name": "no sku", "price_cents": 100},
        headers={"X-QA-Client-Id": client_id},
    )
    retry_after = limited.headers.get("Retry-After")

    assert limited.status_code == 429
    assert retry_after is not None
    assert 0 < int(retry_after) <= math.ceil(settings.rate_limit_write_window_seconds)


@pytest.mark.api
def test_budget_does_not_block_status_updates(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    """Record current scope: only catalog creation is rate limited."""

    created = owner_auth.post(
        items_path(namespace.slug),
        json={"sku": "QA8-PATCH-BUDGET-001", "name": "budget", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id("creator")},
    )
    assert created.status_code == 201
    item_id = int(created.json()["id"])

    shared_client = unique_client_id("shared")
    _exhaust_budget(owner_auth, namespace, settings, shared_client)

    transition = owner_auth.request(
        "PATCH",
        f"{items_path(namespace.slug)}/{item_id}",
        json={"status": "archived"},
        headers={"X-QA-Client-Id": shared_client},
    )

    assert transition.status_code == 200
    assert transition.json()["status"] == "archived"
    attach_json(
        "Update bypasses the create budget",
        {"item": transition.json(), "client": shared_client},
    )
