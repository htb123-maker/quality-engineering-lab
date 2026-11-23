"""Real Android commerce flow whose final facts come from the SUT."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import allure
import pytest
from qa_core.cache import read_commerce_read_model
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory, CommerceApiFactory
from qa_core.db import DatabaseClient
from qa_core.e2e import FixtureSessionApi
from qa_core.platforms.android import AndroidFixtureAdapter
from qa_core.resource_pools import NamespaceLease


@pytest.mark.e2e
@pytest.mark.android
@pytest.mark.timeout(900)
def test_android_order_payment_fulfillment_is_verified_by_postgresql(
    android_e2e_adapter: AndroidFixtureAdapter,
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
    settings: Settings,
    sut_api_url: str,
    database: DatabaseClient,
) -> None:
    """Prove one mobile commerce chain has real database and Redis facts."""

    auth = catalog_items.auth
    item = catalog_items.create(
        name="Android commerce item",
        price_cents=1299,
    )
    assert item.status_code == 201
    item_id = int(item.json()["id"])
    commerce = CommerceApiFactory(
        auth=auth,
        workspace_slug=catalog_items.workspace_slug,
        client_id="week33-android-commerce",
    )
    inventory = commerce.set_inventory(item_id, 3)
    assert inventory.status_code == 200

    fixture_api = FixtureSessionApi(
        auth,
        base_url=sut_api_url,
        client_id="week33-android-commerce-session",
    )
    session, _ = fixture_api.create(item_id)
    initial = android_e2e_adapter.commerce.open(
        base_url=str(settings.android_e2e_api_base_url).rstrip("/"),
        session_id=session.session_id,
    )
    assert initial.status == "active"

    created = android_e2e_adapter.commerce.create_order()
    assert created.status == "AWAITING_PAYMENT"
    assert created.available == 2

    paid = android_e2e_adapter.commerce.pay()
    assert paid.status == "PAID"

    fulfilled = android_e2e_adapter.commerce.fulfill()
    assert fulfilled.status == "FULFILLED"
    assert fulfilled.available == 2

    server = commerce.order(fulfilled.order_id)
    assert server.status_code == 200
    assert server.json()["status"] == "FULFILLED"

    fact = database.fetch_one(
        """
        SELECT
            o.status,
            p.status AS payment_status,
            r.status AS reservation_status,
            i.on_hand,
            i.reserved,
            (SELECT COUNT(*) FROM order_events e
             WHERE e.order_id = o.id) AS event_count
        FROM orders AS o
        JOIN payments AS p ON p.order_id = o.id
        JOIN inventory_reservations AS r ON r.order_id = o.id
        JOIN inventory AS i
          ON i.workspace_id = o.workspace_id
         AND i.item_id = r.item_id
        WHERE o.id = %s
        """,
        (fulfilled.order_id,),
    )
    assert fact == {
        "status": "FULFILLED",
        "payment_status": "SUCCEEDED",
        "reservation_status": "CONSUMED",
        "on_hand": 2,
        "reserved": 0,
        "event_count": 3,
    }

    read_model = read_commerce_read_model(
        str(settings.redis_url),
        namespace.workspace_id,
        fulfilled.order_id,
    )
    assert read_model is not None
    assert read_model["status"] == "FULFILLED"

    allure.attach(
        (
            f"item_id={item_id}\n"
            f"order_id={fulfilled.order_id}\n"
            f"ui_status={fulfilled.status}\n"
            f"api_status={server.json()['status']}\n"
            "postgres_status=FULFILLED\n"
            "reservation=CONSUMED\n"
            "on_hand=2\n"
        ),
        name="android-commerce-sut-evidence",
        attachment_type=allure.attachment_type.TEXT,
    )
