"""Commerce idempotency survives a real API timeout and retry."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import uuid

import httpx
import pytest
from pydantic import AnyHttpUrl
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory, CommerceApiFactory
from qa_core.db import DatabaseClient
from qa_core.resilience import ToxiproxyClient
from qa_core.resilience.toxiproxy import latency_toxic
from qa_core.resource_pools import NamespaceLease


@pytest.mark.api
@pytest.mark.fault_injection
@pytest.mark.recovery
def test_payment_retry_after_latency_has_one_settlement(
    catalog_items: CatalogApiFactory,
    commerce: CommerceApiFactory,
    fault_proxy: tuple[ToxiproxyClient, str, str],
    settings: Settings,
    database: DatabaseClient,
    namespace: NamespaceLease,
) -> None:
    item_id = int(catalog_items.create(price_cents=1500).json()["id"])
    commerce.set_inventory(item_id, 2)
    created = commerce.create_order(item_id, quantity=2)
    assert created.status_code == 201
    order_id = int(created.json()["order_id"])

    toxiproxy, proxy_name, proxy_url = fault_proxy
    proxy_settings = settings.model_copy(
        update={
            "api_base_url": AnyHttpUrl(proxy_url),
            "api_read_timeout_seconds": 0.5,
            "api_write_timeout_seconds": 0.5,
            "api_retry_max_attempts": 1,
            "api_retry_backoff_seconds": 0.0,
        }
    )
    key = uuid.uuid4().hex
    proxy_auth = AuthClient.from_settings(proxy_settings)
    proxy_commerce = CommerceApiFactory(
        auth=proxy_auth,
        workspace_slug=commerce.workspace_slug,
        client_id="week33-commerce-weak-network",
    )
    try:
        proxy_auth.login(
            namespace.owner_email,
            settings.auth_test_password,
        )
        toxiproxy.add_toxic(
            proxy_name,
            latency_toxic(latency_ms=1_500, name="week33-commerce-latency"),
        )
        with pytest.raises(httpx.HTTPError):
            proxy_commerce.pay(order_id, idempotency_key=key)

        toxiproxy.remove_toxic(proxy_name, "week33-commerce-latency")
        retried = proxy_commerce.pay(order_id, idempotency_key=key)
    finally:
        proxy_auth.close()

    assert retried.status_code == 200
    assert retried.json()["status"] == "PAID"
    payments = database.fetch_one(
        "SELECT COUNT(*) AS payments FROM payments WHERE order_id = %s",
        (order_id,),
    )
    assert payments == {"payments": 1}
