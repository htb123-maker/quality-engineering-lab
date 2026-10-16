"""Cross-namespace isolation tests for parallel-safe API data."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory, NamespaceFactory
from qa_core.resource_pools import NamespaceLease

from tests.api.conftest import (
    ATLAS_SLUG,
    ORBIT_SLUG,
    attach_json,
    item_path,
    items_path,
    owner_session,
    unique_client_id,
)


def _error_code(response: httpx.Response) -> str | None:
    payload = response.json()
    return payload.get("error") if isinstance(payload, dict) else None


@pytest.mark.api
def test_two_namespaces_can_hold_the_same_sku(
    catalog_items: CatalogApiFactory,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    sku = catalog_items.new_sku("SHARED")
    created = catalog_items.create(sku=sku)

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        peer_items = CatalogApiFactory(
            auth=peer_auth,
            workspace_slug=peer_namespace.slug,
            client_id=unique_client_id("peer"),
        )
        peer_created = peer_items.create(sku=sku)

    assert created.status_code == 201
    assert peer_created.status_code == 201
    assert created.json()["id"] != peer_created.json()["id"]
    attach_json(
        "Same SKU in two namespaces",
        {
            "primary": {"workspace": catalog_items.workspace_slug, "sku": sku},
            "peer": {"workspace": peer_namespace.slug, "sku": sku},
        },
    )


@pytest.mark.api
def test_catalog_listing_only_returns_own_items(
    catalog_items: CatalogApiFactory,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    own_sku = catalog_items.new_sku("OWN")
    assert catalog_items.create(sku=own_sku).status_code == 201

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        peer_items = CatalogApiFactory(
            auth=peer_auth,
            workspace_slug=peer_namespace.slug,
            client_id=unique_client_id("peer"),
        )
        peer_catalog = peer_items.catalog_items()

    own_skus = {item["sku"] for item in catalog_items.catalog_items()}
    assert own_skus == {own_sku}
    assert peer_catalog == []


@pytest.mark.api
def test_idempotency_keys_are_scoped_per_workspace(
    catalog_items: CatalogApiFactory,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    key = uuid4().hex
    own = catalog_items.create(price_cents=1000, idempotency_key=key)

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        peer = CatalogApiFactory(
            auth=peer_auth,
            workspace_slug=peer_namespace.slug,
            client_id=unique_client_id("peer"),
        ).create(sku=catalog_items.new_sku("PEER"), price_cents=2000, idempotency_key=key)

    assert own.status_code == 201
    assert peer.status_code == 201
    assert peer.headers.get("Idempotent-Replay") is None
    attach_json(
        "Idempotency key reuse across workspaces",
        {"key": key, "own": own.json(), "peer": peer.json()},
    )


@pytest.mark.api
def test_item_ids_are_not_addressable_from_another_workspace(
    catalog_items: CatalogApiFactory,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    created = catalog_items.create()
    item_id = int(created.json()["id"])

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        response = peer_auth.request(
            "PATCH",
            item_path(item_id, peer_namespace.slug),
            json={"status": "archived"},
            headers={"X-QA-Client-Id": unique_client_id("peer")},
        )

    assert response.status_code == 404
    assert _error_code(response) == "item_not_found"
    assert catalog_items.catalog_items()[0]["status"] == "active"
    attach_json("Cross-workspace item patch", response.json())


@pytest.mark.api
def test_cross_workspace_delete_is_not_found(
    catalog_items: CatalogApiFactory,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    created = catalog_items.create()
    item_id = int(created.json()["id"])

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        response = peer_auth.request(
            "DELETE",
            item_path(item_id, peer_namespace.slug),
            headers={"X-QA-Client-Id": unique_client_id("peer")},
        )

    assert response.status_code == 404
    assert _error_code(response) == "item_not_found"
    assert len(catalog_items.catalog_items()) == 1


@pytest.mark.api
def test_owner_of_one_namespace_cannot_write_to_another(
    owner_auth: AuthClient,
    peer_namespace: NamespaceLease,
) -> None:
    response = owner_auth.post(
        items_path(peer_namespace.slug),
        json={"sku": "QA8-FOREIGN-001", "name": "nope", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id("foreign")},
    )

    assert response.status_code == 403
    assert _error_code(response) == "permission_denied"
    attach_json("Foreign workspace write", response.json())


@pytest.mark.api
def test_rate_limit_budget_is_tracked_per_client_id(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    exhausted_client = unique_client_id("budget")
    invalid_body = {"name": "no sku", "price_cents": 100}
    exhausted_headers = {"X-QA-Client-Id": exhausted_client}

    for _ in range(settings.rate_limit_write_max):
        accepted = owner_auth.post(
            items_path(namespace.slug),
            json=invalid_body,
            headers=exhausted_headers,
        )
        assert accepted.status_code == 422
    blocked = owner_auth.post(
        items_path(namespace.slug),
        json=invalid_body,
        headers=exhausted_headers,
    )

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        fresh_client_response = peer_auth.post(
            items_path(peer_namespace.slug),
            json=invalid_body,
            headers={"X-QA-Client-Id": unique_client_id("fresh")},
        )
        still_blocked = peer_auth.post(
            items_path(peer_namespace.slug),
            json=invalid_body,
            headers=exhausted_headers,
        )

    assert blocked.status_code == 429
    assert fresh_client_response.status_code == 422
    assert still_blocked.status_code == 429
    attach_json(
        "Rate limit isolation",
        {
            "exhausted_client": exhausted_client,
            "blocked_status": blocked.status_code,
            "fresh_client_status": fresh_client_response.status_code,
            "other_workspace_status": still_blocked.status_code,
        },
    )


@pytest.mark.api
def test_item_status_does_not_leak_between_namespaces(
    catalog_items: CatalogApiFactory,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    own = catalog_items.create().json()
    catalog_items.set_status(int(own["id"]), "archived")

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        peer_items = CatalogApiFactory(
            auth=peer_auth,
            workspace_slug=peer_namespace.slug,
            client_id=unique_client_id("peer"),
        )
        peer = peer_items.create().json()

    own_statuses = [item["status"] for item in catalog_items.catalog_items()]
    assert own_statuses == ["archived"]
    assert peer["status"] == "active"


@pytest.mark.api
def test_canonical_seed_catalog_is_untouched_by_isolated_writes(
    catalog_items: CatalogApiFactory,
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> None:
    before = namespace_factory.seed_counts()
    assert catalog_items.create().status_code == 201
    assert catalog_items.create().status_code == 201
    after = namespace_factory.seed_counts()

    assert before == {"workspaces": 2, "users": 3, "items": 4}
    assert after == before

    with owner_session(settings.auth_test_username, settings) as atlas_auth:
        atlas_catalog = atlas_auth.get(f"/api/v1/workspaces/{ATLAS_SLUG}/catalog").json()
        orbit_catalog = atlas_auth.get(f"/api/v1/workspaces/{ORBIT_SLUG}/catalog")

    assert atlas_catalog["count"] == 3
    assert orbit_catalog.status_code == 200


@pytest.mark.api
def test_lease_exposes_a_private_workspace(namespace: NamespaceLease) -> None:
    assert namespace.slug.startswith("qa-ns-")
    assert namespace.slug not in {ATLAS_SLUG, ORBIT_SLUG}
    assert namespace.workspace_id > 0
    assert namespace.owner_email.endswith(f"@{namespace.slug}.example")
    attach_json(
        "Namespace lease",
        {
            "label": namespace.label,
            "slug": namespace.slug,
            "workspace_id": namespace.workspace_id,
            "owner_email": namespace.owner_email,
            "reused": namespace.reused,
        },
    )
