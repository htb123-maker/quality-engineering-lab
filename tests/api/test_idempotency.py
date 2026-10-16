"""Idempotency-key tests for catalog item creation."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from uuid import uuid4

import pytest

from tests.api.conftest import CatalogItemFactory, attach_json


def _count_sku(items: list[dict[str, object]], sku: str) -> int:
    return sum(1 for item in items if item.get("sku") == sku)


@pytest.mark.api
def test_repeated_key_and_body_replays_the_first_response(
    catalog_items: CatalogItemFactory,
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
    catalog_items: CatalogItemFactory,
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
    catalog_items: CatalogItemFactory,
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
