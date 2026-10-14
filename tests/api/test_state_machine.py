"""State-machine and authorization tests for catalog items."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import pytest
from qa_core.auth import AuthClient
from qa_core.contracts import ValidationErrorResponse, validate_contract
from qa_core.data_factories import CatalogApiFactory, items_path
from qa_core.resource_pools import NamespaceLease

from tests.api.conftest import (
    attach_json,
    unique_client_id,
)


@pytest.mark.api
def test_active_item_can_be_archived(
    catalog_items: CatalogApiFactory,
) -> None:
    created = catalog_items.create()
    assert created.status_code == 201
    item = created.json()
    assert item["status"] == "active"

    archived = catalog_items.set_status(item["id"], "archived")

    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["id"] == item["id"]
    attach_json("Archived item", archived.json())


@pytest.mark.api
def test_archiving_an_archived_item_is_rejected(
    catalog_items: CatalogApiFactory,
) -> None:
    item = catalog_items.create().json()
    catalog_items.set_status(item["id"], "archived")

    again = catalog_items.set_status(item["id"], "archived")

    assert again.status_code == 409
    assert again.json()["error"] == "invalid_state_transition"
    attach_json("Re-archive rejected", again.json())


@pytest.mark.api
def test_restoring_an_archived_item_is_rejected(
    catalog_items: CatalogApiFactory,
) -> None:
    item = catalog_items.create().json()
    catalog_items.set_status(item["id"], "archived")

    restore = catalog_items.set_status(item["id"], "active")

    assert restore.status_code == 409
    assert restore.json()["error"] == "invalid_state_transition"
    attach_json("Restore rejected", restore.json())


@pytest.mark.api
def test_archiving_an_active_item_again_is_rejected(
    catalog_items: CatalogApiFactory,
) -> None:
    item = catalog_items.create().json()

    noop = catalog_items.set_status(item["id"], "active")

    assert noop.status_code == 409
    assert noop.json()["error"] == "invalid_state_transition"


@pytest.mark.api
def test_unknown_status_value_is_a_validation_error(
    catalog_items: CatalogApiFactory,
) -> None:
    item = catalog_items.create().json()

    response = catalog_items.set_status(item["id"], "deleted")

    assert response.status_code == 422
    validation = validate_contract(ValidationErrorResponse, response.json())
    assert [field.field for field in validation.fields] == ["$.status"]
    attach_json("Unknown status", validation.model_dump(mode="json"))


@pytest.mark.api
def test_transition_on_unknown_item_is_not_found(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.set_status(2_000_000_000, "archived")

    assert response.status_code == 404
    assert response.json()["error"] == "item_not_found"
    attach_json("Unknown item transition", response.json())


@pytest.mark.api
def test_viewer_cannot_create_a_catalog_item(
    viewer_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    response = viewer_auth.post(
        items_path(namespace.slug),
        json={"sku": "QA8-VIEWER-001", "name": "nope", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id("viewer")},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "permission_denied"
    attach_json("Viewer write rejected", response.json())


@pytest.mark.api
def test_owner_cannot_write_to_another_workspace(
    atlas_owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    response = atlas_owner_auth.post(
        items_path(namespace.slug),
        json={"sku": "QA8-CROSS-001", "name": "nope", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id("orbit")},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "permission_denied"
    attach_json("Cross-workspace write rejected", response.json())


@pytest.mark.api
@pytest.mark.parametrize(
    ("first_status", "second_status"),
    [
        ("archived", "active"),
        ("active", "active"),
        ("archived", "archived"),
    ],
)
def test_only_active_to_archived_is_allowed(
    catalog_items: CatalogApiFactory,
    first_status: str,
    second_status: str,
) -> None:
    item = catalog_items.create().json()
    item_id = int(item["id"])
    if first_status == "archived":
        assert catalog_items.set_status(item_id, "archived").status_code == 200

    response = catalog_items.set_status(item_id, second_status)

    assert response.status_code == 409
    assert response.json()["error"] == "invalid_state_transition"
    attach_json(
        "Illegal transition",
        {"from": first_status, "to": second_status, "body": response.json()},
    )


@pytest.mark.api
def test_archived_item_stays_archived_in_the_catalog(
    catalog_items: CatalogApiFactory,
) -> None:
    item = catalog_items.create().json()
    catalog_items.set_status(int(item["id"]), "archived")

    catalog = catalog_items.catalog_items()

    assert [entry["status"] for entry in catalog] == ["archived"]
    assert catalog[0]["id"] == item["id"]


@pytest.mark.api
def test_viewer_cannot_transition_an_item_status(
    namespace: NamespaceLease,
    viewer_auth: AuthClient,
    catalog_items: CatalogApiFactory,
) -> None:
    item = catalog_items.create().json()

    response = viewer_auth.request(
        "PATCH",
        f"{items_path(namespace.slug)}/{item['id']}",
        json={"status": "archived"},
        headers={"X-QA-Client-Id": unique_client_id("viewer-patch")},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "permission_denied"
    attach_json("Viewer transition rejected", response.json())


@pytest.mark.api
def test_delete_then_transition_is_not_found(
    catalog_items: CatalogApiFactory,
) -> None:
    item = catalog_items.create().json()
    item_id = int(item["id"])
    assert catalog_items.delete(item_id).status_code == 204

    response = catalog_items.set_status(item_id, "archived")

    assert response.status_code == 404
    assert response.json()["error"] == "item_not_found"
