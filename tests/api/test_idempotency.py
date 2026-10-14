"""Idempotency-key tests for catalog item creation."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from uuid import uuid4

import pytest
from qa_core.data_factories import CatalogApiFactory

from tests.api.conftest import attach_json


def _count_sku(items: list[dict[str, object]], sku: str) -> int:
    return sum(1 for item in items if item.get("sku") == sku)


@pytest.mark.api
def test_repeated_key_and_body_replays_the_first_response(
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("IDEM")
    key = uuid4().hex

    first = catalog_items.create(sku=sku, price_cents=1000, idempotency_key=key)
    second = catalog_items.create(
        sku=sku,
        price_cents=1000,
        idempotency_key=key,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.headers.get("Idempotent-Replay") == "true"
    assert _count_sku(catalog_items.catalog_items(), sku) == 1
    attach_json(
        "Idempotent replay",
        {
            "first": first.json(),
            "replay_status": second.status_code,
            "replay_header": second.headers.get("Idempotent-Replay"),
        },
    )


@pytest.mark.api
def test_same_key_with_different_body_is_a_conflict(
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("IDEM2")
    key = uuid4().hex

    first = catalog_items.create(sku=sku, price_cents=1000, idempotency_key=key)
    conflict = catalog_items.create(
        sku=sku,
        price_cents=2000,
        idempotency_key=key,
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"] == "idempotency_conflict"
    assert _count_sku(catalog_items.catalog_items(), sku) == 1
    attach_json("Idempotency conflict", conflict.json())


@pytest.mark.api
def test_without_a_key_creation_is_re_executed(
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("NOKEY")

    first = catalog_items.create(sku=sku)
    second = catalog_items.create(sku=sku)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"] == "sku_conflict"
    assert _count_sku(catalog_items.catalog_items(), sku) == 1
    attach_json(
        "Non-idempotent duplicate",
        {"first_status": first.status_code, "second": second.json()},
    )


@pytest.mark.api
def test_third_replay_returns_the_first_response(
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("TRIPLE")
    key = uuid4().hex

    first = catalog_items.create(sku=sku, price_cents=700, idempotency_key=key)
    second = catalog_items.create(sku=sku, price_cents=700, idempotency_key=key)
    third = catalog_items.create(sku=sku, price_cents=700, idempotency_key=key)

    assert first.status_code == second.status_code == third.status_code == 201
    assert first.json() == second.json() == third.json()
    assert second.headers.get("Idempotent-Replay") == "true"
    assert third.headers.get("Idempotent-Replay") == "true"
    assert _count_sku(catalog_items.catalog_items(), sku) == 1


@pytest.mark.api
def test_replay_does_not_create_a_second_row(
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("NOROW")
    key = uuid4().hex
    before = len(catalog_items.catalog_items())

    catalog_items.create(sku=sku, idempotency_key=key)
    catalog_items.create(sku=sku, idempotency_key=key)
    after = len(catalog_items.catalog_items())

    assert after == before + 1


@pytest.mark.api
def test_distinct_keys_create_distinct_items(
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("TWOKEYS")

    first = catalog_items.create(sku=sku, idempotency_key=uuid4().hex)
    assert first.status_code == 201
    second = catalog_items.create(sku=sku, idempotency_key=uuid4().hex)

    assert second.status_code == 409
    assert second.json()["error"] == "sku_conflict"
    assert _count_sku(catalog_items.catalog_items(), sku) == 1


@pytest.mark.api
def test_replay_after_delete_returns_the_cached_response(
    catalog_items: CatalogApiFactory,
) -> None:
    """Pin the current cache semantics: replay does not re-check the database.

    The idempotency record lives in Redis with its own TTL, so a replay after
    the row was deleted still returns the original 201 payload. Week 10 (cache
    consistency) revisits this boundary.
    """

    sku = catalog_items.new_sku("DELETED")
    key = uuid4().hex
    first = catalog_items.create(sku=sku, idempotency_key=key)
    item_id = int(first.json()["id"])

    deleted = catalog_items.delete(item_id)
    replay = catalog_items.create(sku=sku, idempotency_key=key)

    assert deleted.status_code == 204
    assert replay.status_code == 201
    assert replay.headers.get("Idempotent-Replay") == "true"
    assert replay.json()["id"] == item_id
    assert _count_sku(catalog_items.catalog_items(), sku) == 0
    attach_json(
        "Replay after delete",
        {
            "replay": replay.json(),
            "catalog_skus": [item["sku"] for item in catalog_items.catalog_items()],
        },
    )
