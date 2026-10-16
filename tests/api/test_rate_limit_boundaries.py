"""Rate-limit boundaries: budgets, headers, scopes, and what is not limited.

Week 7 proved that the write budget eventually answers 429 with ``Retry-After``.
Week 11 asks the harder questions: does the response advertise the budget
before it trips, does rotating the spoofable client header buy more budget, and
which endpoints are deliberately outside the limiter?
"""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import allure
import httpx
import pytest
from qa_core.api_errors import classify_response
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import items_path
from qa_core.resource_pools import NamespaceLease
from qa_core.security import parse_rate_limit_headers, retry_after_seconds

from tests.api.conftest import attach_json, unique_client_id

INVALID_BODY = {"name": "no sku", "price_cents": 100}


def _writes(
    auth: AuthClient,
    namespace: NamespaceLease,
    count: int,
    *,
    client_id: str,
) -> list[httpx.Response]:
    """Send ``count`` writes that fail validation but still cost budget."""

    responses = []
    for _ in range(count):
        responses.append(
            auth.post(
                items_path(namespace.slug),
                json=INVALID_BODY,
                headers={"X-QA-Client-Id": client_id},
            )
        )
    return responses


@allure.epic("Quality Engineering Lab")
@allure.feature("Rate limiting")
@allure.story("Budget headers")
@pytest.mark.api
def test_accepted_writes_advertise_the_remaining_budget(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    client_id = unique_client_id("budget-headers")

    first = owner_auth.post(
        items_path(namespace.slug),
        json={"sku": "QA11-BUDGET-0001", "name": "budget", "price_cents": 100},
        headers={"X-QA-Client-Id": client_id},
    )
    budget = parse_rate_limit_headers(first)

    assert first.status_code == 201
    assert budget is not None, first.headers
    assert budget.limit == settings.rate_limit_write_max
    assert budget.scope == "client"
    assert budget.remaining == settings.rate_limit_write_max - 1
    assert budget.reset_after > 0
    attach_json(
        "Advertised budget",
        {
            "limit": budget.limit,
            "remaining": budget.remaining,
            "reset_after": budget.reset_after,
            "scope": budget.scope,
        },
    )


@allure.feature("Rate limiting")
@allure.story("Budget headers")
@pytest.mark.api
def test_remaining_budget_counts_down_to_the_429(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    client_id = unique_client_id("countdown")
    remaining: list[int] = []

    for _ in range(settings.rate_limit_write_max):
        response = owner_auth.post(
            items_path(namespace.slug),
            json=INVALID_BODY,
            headers={"X-QA-Client-Id": client_id},
        )
        budget = parse_rate_limit_headers(response)
        assert response.status_code == 422
        assert budget is not None
        remaining.append(budget.remaining)

    limited = owner_auth.post(
        items_path(namespace.slug),
        json=INVALID_BODY,
        headers={"X-QA-Client-Id": client_id},
    )
    limited_budget = parse_rate_limit_headers(limited)

    assert remaining == list(
        range(settings.rate_limit_write_max - 1, -1, -1)
    )
    assert limited.status_code == 429
    assert limited_budget is not None
    assert limited_budget.exhausted
    assert retry_after_seconds(limited) == limited_budget.reset_after
    assert classify_response(limited).category == "environment"
    attach_json(
        "Countdown",
        {
            "remaining": remaining,
            "status": limited.status_code,
            "retry_after": limited.headers.get("Retry-After"),
        },
    )


@allure.feature("Rate limiting")
@allure.story("Spoof resistance")
@pytest.mark.api
def test_rotating_the_client_header_still_hits_the_principal_budget(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    """``X-QA-Client-Id`` is caller-controlled, so a second bucket backs it up."""

    statuses: list[int] = []
    for index in range(settings.rate_limit_principal_max):
        response = owner_auth.post(
            items_path(namespace.slug),
            json=INVALID_BODY,
            headers={"X-QA-Client-Id": f"rotating-{index}-{unique_client_id('r')}"},
        )
        statuses.append(response.status_code)

    limited = owner_auth.post(
        items_path(namespace.slug),
        json=INVALID_BODY,
        headers={"X-QA-Client-Id": unique_client_id("rotating-final")},
    )
    budget = parse_rate_limit_headers(limited)

    assert set(statuses) == {422}
    assert limited.status_code == 429
    assert budget is not None
    assert budget.scope == "principal"
    assert limited.json()["error"] == "rate_limited"
    assert limited.json()["message"].endswith("principal.")
    attach_json(
        "Principal bucket",
        {
            "rotated_clients": len(statuses),
            "principal_limit": budget.limit,
            "status": limited.status_code,
            "body": limited.json(),
        },
    )


@allure.feature("Rate limiting")
@allure.story("Scope")
@pytest.mark.api
def test_reads_are_not_charged_against_the_write_budget(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    client_id = unique_client_id("read-scope")
    _writes(owner_auth, namespace, settings.rate_limit_write_max, client_id=client_id)

    blocked_write = owner_auth.post(
        items_path(namespace.slug),
        json=INVALID_BODY,
        headers={"X-QA-Client-Id": client_id},
    )
    reads = [
        owner_auth.get(f"/api/v1/workspaces/{namespace.slug}/catalog")
        for _ in range(5)
    ]

    assert blocked_write.status_code == 429
    assert {response.status_code for response in reads} == {200}
    attach_json(
        "Read scope",
        {"write": blocked_write.status_code, "reads": [r.status_code for r in reads]},
    )


@allure.feature("Rate limiting")
@allure.story("Scope")
@pytest.mark.api
def test_denied_writes_do_not_consume_the_budget(
    namespace: NamespaceLease,
    viewer_auth: AuthClient,
    owner_auth: AuthClient,
) -> None:
    """Authorization runs first, so a 403 never burns the caller's budget."""

    client_id = unique_client_id("denied")
    denied = viewer_auth.post(
        items_path(namespace.slug),
        json=INVALID_BODY,
        headers={"X-QA-Client-Id": client_id},
    )
    accepted = owner_auth.post(
        items_path(namespace.slug),
        json={"sku": "QA11-SCOPE-0001", "name": "scoped", "price_cents": 100},
        headers={"X-QA-Client-Id": client_id},
    )
    budget = parse_rate_limit_headers(accepted)

    assert denied.status_code == 403
    assert accepted.status_code == 201
    assert budget is not None
    assert budget.remaining > 0
    attach_json(
        "Denied writes are free",
        {"denied": denied.status_code, "remaining": budget.remaining},
    )


@allure.feature("Rate limiting")
@allure.story("Scope")
@pytest.mark.api
def test_budget_is_tracked_per_principal(
    owner_auth: AuthClient,
    role_sessions: dict[str, AuthClient],
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    """Two different members do not share one client id's budget."""

    shared_client = unique_client_id("shared-principal")
    _writes(
        owner_auth,
        namespace,
        settings.rate_limit_write_max,
        client_id=shared_client,
    )

    blocked = owner_auth.post(
        items_path(namespace.slug),
        json=INVALID_BODY,
        headers={"X-QA-Client-Id": shared_client},
    )
    other = role_sessions["admin"].post(
        items_path(namespace.slug),
        json={"sku": "QA11-PRINCIPAL-0001", "name": "other", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id("other-principal")},
    )

    assert blocked.status_code == 429
    assert other.status_code == 201
