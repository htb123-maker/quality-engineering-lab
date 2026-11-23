"""Real commerce invariants: stock, payment, fulfillment, and compensation."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import redis
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.contracts import CommerceOrder, validate_contract
from qa_core.data_factories import (
    CatalogApiFactory,
    CommerceApiFactory,
    inventory_path,
    orders_path,
)
from qa_core.db import DatabaseClient
from qa_core.resource_pools import NamespaceLease

from tests.api.conftest import unique_client_id


def _order(response_json: dict[str, object]) -> CommerceOrder:
    return validate_contract(CommerceOrder, response_json)


@pytest.mark.api
def test_order_payment_fulfillment_updates_database_and_read_model(
    catalog_items: CatalogApiFactory,
    commerce: CommerceApiFactory,
    database: DatabaseClient,
    namespace: NamespaceLease,
    settings: Settings,
) -> None:
    item = catalog_items.create(price_cents=1299).json()
    item_id = int(item["id"])

    inventory = commerce.set_inventory(item_id, 5)
    assert inventory.status_code == 200
    assert inventory.json()["available"] == 5

    created = commerce.create_order(
        item_id,
        quantity=2,
        idempotency_key=uuid4().hex,
    )
    assert created.status_code == 201
    order = _order(created.json())
    assert order.status == "AWAITING_PAYMENT"
    assert order.total_cents == 2598

    reserved = commerce.inventory(item_id)
    assert reserved.status_code == 200
    assert reserved.json()["reserved"] == 2
    assert reserved.json()["available"] == 3

    paid = commerce.pay(order.order_id, idempotency_key=uuid4().hex)
    assert paid.status_code == 200
    paid_order = _order(paid.json())
    assert paid_order.status == "PAID"
    assert paid_order.payment_status == "SUCCEEDED"

    fulfilled = commerce.fulfill(order.order_id)
    assert fulfilled.status_code == 200
    fulfilled_order = _order(fulfilled.json())
    assert fulfilled_order.status == "FULFILLED"
    assert fulfilled_order.inventory.on_hand == 3
    assert fulfilled_order.inventory.reserved == 0

    fact = database.fetch_one(
        """
        SELECT
            o.status,
            o.total_cents,
            p.status AS payment_status,
            r.status AS reservation_status,
            (SELECT COUNT(*) FROM order_events e
             WHERE e.order_id = o.id) AS event_count
        FROM orders AS o
        JOIN payments AS p ON p.order_id = o.id
        JOIN inventory_reservations AS r ON r.order_id = o.id
        WHERE o.id = %s
        """,
        (order.order_id,),
    )
    assert fact == {
        "status": "FULFILLED",
        "total_cents": 2598,
        "payment_status": "SUCCEEDED",
        "reservation_status": "CONSUMED",
        "event_count": 3,
    }

    client = redis.Redis.from_url(str(settings.redis_url), decode_responses=True)
    try:
        cached = client.get(
            f"commerce:order:{namespace.workspace_id}:{order.order_id}"
        )
    finally:
        client.close()
    assert cached is not None
    assert json.loads(cached)["status"] == "FULFILLED"


@pytest.mark.api
def test_same_order_idempotency_key_does_not_reserve_twice(
    catalog_items: CatalogApiFactory,
    commerce: CommerceApiFactory,
    database: DatabaseClient,
) -> None:
    item_id = int(catalog_items.create().json()["id"])
    commerce.set_inventory(item_id, 3)
    key = uuid4().hex

    first = commerce.create_order(item_id, idempotency_key=key)
    replay = commerce.create_order(item_id, idempotency_key=key)

    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json()["order_id"] == replay.json()["order_id"]
    inventory = commerce.inventory(item_id).json()
    assert inventory["reserved"] == 1
    count = database.fetch_one(
        "SELECT COUNT(*) AS orders FROM orders WHERE id = %s",
        (int(first.json()["order_id"]),),
    )
    assert count == {"orders": 1}


@pytest.mark.api
def test_reused_order_key_with_different_body_is_rejected(
    catalog_items: CatalogApiFactory,
    commerce: CommerceApiFactory,
) -> None:
    item_id = int(catalog_items.create().json()["id"])
    commerce.set_inventory(item_id, 3)
    key = uuid4().hex

    assert commerce.create_order(
        item_id,
        quantity=1,
        idempotency_key=key,
    ).status_code == 201
    conflict = commerce.create_order(
        item_id,
        quantity=2,
        idempotency_key=key,
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"] == "idempotency_conflict"
    assert commerce.inventory(item_id).json()["reserved"] == 1


@pytest.mark.api
def test_insufficient_stock_leaves_no_permanent_reservation(
    catalog_items: CatalogApiFactory,
    commerce: CommerceApiFactory,
    database: DatabaseClient,
    namespace: NamespaceLease,
) -> None:
    item_id = int(catalog_items.create().json()["id"])
    commerce.set_inventory(item_id, 1)

    response = commerce.create_order(item_id, quantity=2)

    assert response.status_code == 409
    assert response.json()["error"] == "insufficient_stock"
    inventory = commerce.inventory(item_id).json()
    assert inventory["reserved"] == 0
    orders = database.fetch_one(
        "SELECT COUNT(*) AS orders FROM orders WHERE workspace_id = %s",
        (namespace.workspace_id,),
    )
    assert orders == {"orders": 0}


@pytest.mark.api
def test_duplicate_payment_key_returns_one_settlement(
    catalog_items: CatalogApiFactory,
    commerce: CommerceApiFactory,
    database: DatabaseClient,
) -> None:
    item_id = int(catalog_items.create().json()["id"])
    commerce.set_inventory(item_id, 2)
    order = commerce.create_order(item_id, quantity=2).json()
    order_id = int(order["order_id"])
    key = uuid4().hex

    first = commerce.pay(order_id, idempotency_key=key)
    replay = commerce.pay(order_id, idempotency_key=key)
    second = commerce.pay(order_id, idempotency_key=uuid4().hex)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json()["payment_id"] == replay.json()["payment_id"]
    assert second.status_code == 409
    assert second.json()["error"] == "order_already_paid"
    payments = database.fetch_one(
        "SELECT COUNT(*) AS payments FROM payments WHERE order_id = %s",
        (order_id,),
    )
    assert payments == {"payments": 1}


@pytest.mark.api
def test_concurrent_payment_attempts_have_one_winner(
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
    settings: Settings,
    database: DatabaseClient,
) -> None:
    item_id = int(catalog_items.create().json()["id"])
    commerce = CommerceApiFactory(
        auth=catalog_items.auth,
        workspace_slug=namespace.slug,
        client_id=unique_client_id("concurrent-commerce"),
    )
    commerce.set_inventory(item_id, 1)
    order_id = int(commerce.create_order(item_id).json()["order_id"])

    def pay_once(index: int) -> tuple[int, dict[str, object]]:
        with AuthClient.from_settings(settings) as auth:
            auth.login(namespace.owner_email, settings.auth_test_password)
            response = auth.post(
                f"{orders_path(namespace.slug, order_id)}/payments",
                json={},
                headers={
                    "Idempotency-Key": f"concurrent-{index}-{uuid4().hex}",
                    "X-QA-Client-Id": unique_client_id(f"payment-{index}"),
                },
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(pay_once, range(2)))

    assert sorted(status for status, _ in results) == [200, 409]
    winner = next(body for status, body in results if status == 200)
    loser = next(body for status, body in results if status == 409)
    assert winner["status"] == "PAID"
    assert loser["error"] == "order_already_paid"
    payments = database.fetch_one(
        "SELECT COUNT(*) AS payments FROM payments WHERE order_id = %s",
        (order_id,),
    )
    assert payments == {"payments": 1}


@pytest.mark.api
def test_cancel_releases_inventory_exactly_once(
    catalog_items: CatalogApiFactory,
    commerce: CommerceApiFactory,
) -> None:
    item_id = int(catalog_items.create().json()["id"])
    commerce.set_inventory(item_id, 4)
    order_id = int(commerce.create_order(item_id, quantity=2).json()["order_id"])

    cancelled = commerce.cancel(order_id)
    repeated = commerce.cancel(order_id)

    assert cancelled.status_code == 200
    assert repeated.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert repeated.json()["status"] == "CANCELLED"
    inventory = commerce.inventory(item_id).json()
    assert inventory["on_hand"] == 4
    assert inventory["reserved"] == 0


@pytest.mark.api
def test_refund_after_payment_restores_inventory_and_payment_state(
    catalog_items: CatalogApiFactory,
    commerce: CommerceApiFactory,
) -> None:
    item_id = int(catalog_items.create().json()["id"])
    commerce.set_inventory(item_id, 3)
    order_id = int(commerce.create_order(item_id, quantity=2).json()["order_id"])
    commerce.pay(order_id)

    refunded = commerce.refund(order_id)

    assert refunded.status_code == 200
    order = _order(refunded.json())
    assert order.status == "REFUNDED"
    assert order.payment_status == "REFUNDED"
    assert order.inventory.on_hand == 3
    assert order.inventory.reserved == 0


@pytest.mark.api
def test_refund_after_fulfillment_restores_on_hand_stock(
    catalog_items: CatalogApiFactory,
    commerce: CommerceApiFactory,
) -> None:
    item_id = int(catalog_items.create().json()["id"])
    commerce.set_inventory(item_id, 2)
    order_id = int(commerce.create_order(item_id).json()["order_id"])
    commerce.pay(order_id)
    commerce.fulfill(order_id)

    refunded = commerce.refund(order_id)

    assert refunded.status_code == 200
    order = _order(refunded.json())
    assert order.status == "REFUNDED"
    assert order.payment_status == "REFUNDED"
    assert order.inventory.on_hand == 2
    assert order.inventory.reserved == 0


@pytest.mark.api
def test_viewer_cannot_change_commerce_inventory(
    viewer_auth: AuthClient,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
) -> None:
    item_id = int(catalog_items.create().json()["id"])

    response = viewer_auth.post(
        inventory_path(namespace.slug),
        json={"item_id": item_id, "on_hand": 10},
        headers={"X-QA-Client-Id": unique_client_id("viewer-commerce")},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "permission_denied"
