"""API writes and reads verified against the real PostgreSQL state."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

import allure
import httpx
import pytest
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory
from qa_core.db import DatabaseClient, WorkspaceRepository
from qa_core.resource_pools import NamespaceLease

from tests.api.conftest import attach_json, owner_session, unique_client_id


def _item_row(
    database: DatabaseClient,
    workspace_id: int,
    sku: str,
) -> dict[str, Any] | None:
    return database.fetch_one(
        """
        SELECT id, workspace_id, sku, name, price_cents, status, created_at
        FROM catalog_items
        WHERE workspace_id = %s AND sku = %s
        """,
        (workspace_id, sku),
    )


def _item_rows(database: DatabaseClient, workspace_id: int, sku: str) -> int:
    row = database.fetch_one(
        """
        SELECT COUNT(*) AS items FROM catalog_items
        WHERE workspace_id = %s AND sku = %s
        """,
        (workspace_id, sku),
    )
    if row is None:
        raise RuntimeError("count query returned no row")
    return int(row["items"])


def _error_code(response: httpx.Response) -> str | None:
    payload = response.json()
    return payload.get("error") if isinstance(payload, dict) else None


def _summary(database: DatabaseClient, workspace_id: int) -> dict[str, Any] | None:
    return database.fetch_one(
        """
        SELECT item_count, catalog_value_cents
        FROM workspace_catalog_summary
        WHERE workspace_id = %s
        """,
        (workspace_id,),
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("API + PostgreSQL")
@allure.story("Create")
@pytest.mark.api
def test_api_create_writes_exactly_one_matching_database_row(
    database: DatabaseClient,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("DBSTATE")
    response = catalog_items.create(
        sku=sku,
        name="Written through the API",
        price_cents=4321,
    )

    assert response.status_code == 201
    row = _item_row(database, namespace.workspace_id, sku)
    assert row is not None
    assert row["id"] == response.json()["id"]
    assert row["sku"] == sku
    assert row["name"] == "Written through the API"
    assert row["price_cents"] == 4321
    assert row["status"] == "active"
    assert row["created_at"] is not None
    assert _item_rows(database, namespace.workspace_id, sku) == 1


@allure.epic("Quality Engineering Lab")
@allure.feature("API + PostgreSQL")
@allure.story("Read")
@pytest.mark.api
def test_api_reads_items_seeded_directly_in_the_database(
    database: DatabaseClient,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
) -> None:
    repository = WorkspaceRepository(database)
    sku = "DBSYNC-0001"
    item_id = repository.upsert_item(
        workspace_id=namespace.workspace_id,
        sku=sku,
        name="Seeded without the API",
        price_cents=777,
    )

    items = catalog_items.catalog_items()
    seeded = [item for item in items if item["sku"] == sku]
    row = _item_row(database, namespace.workspace_id, sku)

    attach_json(
        "Database row and API payload",
        {
            "database": {
                key: value.isoformat() if isinstance(value, datetime) else value
                for key, value in (row or {}).items()
            },
            "api": seeded,
        },
    )
    assert len(seeded) == 1
    assert seeded[0]["id"] == item_id
    assert seeded[0]["name"] == "Seeded without the API"
    assert seeded[0]["price_cents"] == 777
    assert seeded[0]["status"] == "active"


@allure.epic("Quality Engineering Lab")
@allure.feature("API + PostgreSQL")
@allure.story("Update")
@pytest.mark.api
def test_api_patch_updates_the_row_and_a_second_archive_conflicts(
    database: DatabaseClient,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("PATCH")
    created = catalog_items.create(sku=sku)
    assert created.status_code == 201
    item_id = int(created.json()["id"])

    archived = catalog_items.set_status(item_id, "archived")
    row = _item_row(database, namespace.workspace_id, sku)
    repeated = catalog_items.set_status(item_id, "archived")

    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert row is not None
    assert row["status"] == "archived"
    assert repeated.status_code == 409
    assert _error_code(repeated) == "invalid_state_transition"
    assert _item_row(database, namespace.workspace_id, sku) == row


@allure.epic("Quality Engineering Lab")
@allure.feature("API + PostgreSQL")
@allure.story("Delete")
@pytest.mark.api
def test_api_delete_removes_the_row_and_a_second_delete_is_not_found(
    database: DatabaseClient,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("DELETE")
    created = catalog_items.create(sku=sku)
    assert created.status_code == 201
    item_id = int(created.json()["id"])

    deleted = catalog_items.delete(item_id)
    repeated = catalog_items.delete(item_id)

    assert deleted.status_code == 204
    assert _item_row(database, namespace.workspace_id, sku) is None
    assert repeated.status_code == 404
    assert _error_code(repeated) == "item_not_found"


@allure.epic("Quality Engineering Lab")
@allure.feature("API + PostgreSQL")
@allure.story("Unique constraint")
@pytest.mark.api
def test_duplicate_sku_conflict_does_not_write_a_second_row(
    database: DatabaseClient,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("DUP")
    first = catalog_items.create(sku=sku)
    duplicate = catalog_items.create(sku=sku)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert _error_code(duplicate) == "sku_conflict"
    assert _item_rows(database, namespace.workspace_id, sku) == 1
    assert duplicate.json()["message"] == f"SKU '{sku}' already exists in this workspace."


@allure.epic("Quality Engineering Lab")
@allure.feature("API + PostgreSQL")
@allure.story("Unique constraint")
@pytest.mark.api
def test_two_concurrent_creates_of_one_sku_are_accepted_exactly_once(
    database: DatabaseClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    sku = f"QA8-RACE-{namespace.workspace_id}"
    barrier = threading.Barrier(2, timeout=10)
    statuses: list[int] = []
    errors: list[str] = []
    lock = threading.Lock()

    def create_in_thread(tag: str) -> None:
        try:
            with owner_session(namespace.owner_email, settings) as auth:
                factory = CatalogApiFactory(
                    auth=auth,
                    workspace_slug=namespace.slug,
                    client_id=unique_client_id(tag),
                )
                barrier.wait()
                response = factory.create(sku=sku, name=f"Race {tag}")
                with lock:
                    statuses.append(response.status_code)
        except Exception as exc:  # noqa: BLE001 - reported through `errors`
            with lock:
                errors.append(f"{type(exc).__name__}: {exc}")

    threads = [
        threading.Thread(target=create_in_thread, args=(tag,), daemon=True)
        for tag in ("race-a", "race-b")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    rows = database.fetch_all(
        """
        SELECT id, name, status FROM catalog_items
        WHERE workspace_id = %s AND sku = %s
        """,
        (namespace.workspace_id, sku),
    )
    attach_json(
        "Concurrent create outcome",
        {"statuses": sorted(statuses), "errors": errors, "rows": rows},
    )

    assert errors == []
    assert sorted(statuses) == [201, 409]
    assert len(rows) == 1
    assert rows[0]["status"] == "active"


@allure.epic("Quality Engineering Lab")
@allure.feature("API + PostgreSQL")
@allure.story("Summary view")
@pytest.mark.api
def test_archiving_through_the_api_changes_the_active_summary_view(
    database: DatabaseClient,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
) -> None:
    first = catalog_items.create(name="Summary first", price_cents=1000)
    second = catalog_items.create(name="Summary second", price_cents=2000)
    assert (first.status_code, second.status_code) == (201, 201)

    before = _summary(database, namespace.workspace_id)
    archived = catalog_items.set_status(int(second.json()["id"]), "archived")
    after = _summary(database, namespace.workspace_id)

    assert archived.status_code == 200
    assert before == {"item_count": 2, "catalog_value_cents": 3000}
    assert after == {"item_count": 1, "catalog_value_cents": 1000}


@allure.epic("Quality Engineering Lab")
@allure.feature("API + PostgreSQL")
@allure.story("Isolation")
@pytest.mark.api
def test_another_workspace_cannot_see_or_touch_these_rows(
    database: DatabaseClient,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
    settings: Settings,
) -> None:
    sku = catalog_items.new_sku("SCOPED")
    created = catalog_items.create(sku=sku)
    assert created.status_code == 201
    item_id = int(created.json()["id"])

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        peer_path = f"/api/v1/workspaces/{peer_namespace.slug}/catalog"
        listing = peer_auth.get(peer_path)
        cross_workspace = peer_auth.request(
            "DELETE",
            f"{peer_path}/items/{item_id}",
            headers={"X-QA-Client-Id": unique_client_id("cross")},
        )

    assert listing.status_code == 200
    assert [item["sku"] for item in listing.json()["items"]] == []
    assert cross_workspace.status_code == 404
    assert _item_row(database, namespace.workspace_id, sku) is not None
