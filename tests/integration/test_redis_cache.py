"""Cache-versus-database consistency, observed on the real Redis keys."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from typing import Any

import allure
import httpx
import pytest
from qa_core.cache import CatalogCacheProbe
from qa_core.config.settings import Settings
from qa_core.data_factories import NamespaceIdentity
from qa_core.db import DatabaseClient


def _first_item(database: DatabaseClient, workspace_id: int) -> dict[str, Any]:
    """Return the first catalog item of one workspace, ordered by id."""

    row = database.fetch_one(
        """
        SELECT id, sku, name, price_cents
        FROM catalog_items
        WHERE workspace_id = %s
        ORDER BY id
        LIMIT 1
        """,
        (workspace_id,),
    )
    if row is None:
        raise AssertionError("the namespace fixture must seed at least one item")
    return row


def _rename_item(
    database: DatabaseClient,
    workspace_id: int,
    item_id: int,
    *,
    name: str,
    price_cents: int,
) -> None:
    """Change a row without going through the API, as a DBA or batch job would."""

    database.execute(
        """
        UPDATE catalog_items
        SET name = %s, price_cents = %s
        WHERE workspace_id = %s AND id = %s
        """,
        (name, price_cents, workspace_id, item_id),
    )


def _served_item(response: httpx.Response, sku: str) -> dict[str, Any]:
    """Return the served catalog item with one SKU."""

    items = response.json()["items"]
    for item in items:
        if item["sku"] == sku:
            return dict(item)
    raise AssertionError(f"catalog response did not contain {sku}")


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis + PostgreSQL")
@allure.story("Stale read")
@pytest.mark.integration
def test_direct_database_change_stays_invisible_until_the_cache_is_invalidated(
    sut_api_url: str,
    settings: Settings,
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
) -> None:
    probe = CatalogCacheProbe(
        redis_url=str(settings.redis_url),
        workspace_slug=db_namespace.slug,
    )
    probe.purge()
    try:
        item = _first_item(database, db_namespace.workspace_id)
        with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
            warm = client.get(f"/api/v1/workspaces/{db_namespace.slug}/catalog")
            _rename_item(
                database,
                db_namespace.workspace_id,
                int(item["id"]),
                name="Renamed behind the cache",
                price_cents=7777,
            )
            stale = client.get(f"/api/v1/workspaces/{db_namespace.slug}/catalog")
            probe.purge()
            fresh = client.get(f"/api/v1/workspaces/{db_namespace.slug}/catalog")

        database_row = database.fetch_one(
            "SELECT name, price_cents FROM catalog_items WHERE id = %s",
            (int(item["id"]),),
        )
        allure.attach(
            "\n".join(
                [
                    f"warm cache state: {warm.headers['X-Cache']}",
                    f"after direct UPDATE: {stale.headers['X-Cache']}",
                    f"after invalidation: {fresh.headers['X-Cache']}",
                    f"served while stale: {_served_item(stale, str(item['sku']))}",
                    f"database row: {database_row}",
                ]
            ),
            name="stale read evidence",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert warm.headers["X-Cache"] == "MISS"
        assert stale.headers["X-Cache"] == "HIT"
        stale_item = _served_item(stale, str(item["sku"]))
        assert stale_item["name"] == item["name"]
        assert stale_item["price_cents"] == item["price_cents"]

        assert database_row is not None
        assert database_row["name"] == "Renamed behind the cache"
        assert database_row["price_cents"] == 7777

        assert fresh.headers["X-Cache"] == "MISS"
        fresh_item = _served_item(fresh, str(item["sku"]))
        assert fresh_item["name"] == "Renamed behind the cache"
        assert fresh_item["price_cents"] == 7777
    finally:
        probe.purge()


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis + PostgreSQL")
@allure.story("TTL bounds staleness")
@pytest.mark.integration
def test_expiry_ends_the_stale_window_created_by_a_direct_write(
    sut_api_url: str,
    settings: Settings,
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
) -> None:
    probe = CatalogCacheProbe(
        redis_url=str(settings.redis_url),
        workspace_slug=db_namespace.slug,
    )
    probe.purge()
    try:
        item = _first_item(database, db_namespace.workspace_id)
        with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
            warm = client.get(f"/api/v1/workspaces/{db_namespace.slug}/catalog")
            assert warm.headers["X-Cache"] == "MISS"
            _rename_item(
                database,
                db_namespace.workspace_id,
                int(item["id"]),
                name="Renamed before the TTL",
                price_cents=4242,
            )
            entry = probe.entry()
            assert entry is not None
            assert probe.expire_soon(entry.key, seconds=1)
            assert probe.wait_until_expired(entry.key), "TTL must remove the entry"
            after_expiry = client.get(f"/api/v1/workspaces/{db_namespace.slug}/catalog")

        assert after_expiry.headers["X-Cache"] == "MISS"
        refreshed = _served_item(after_expiry, str(item["sku"]))
        assert refreshed["name"] == "Renamed before the TTL"
        assert refreshed["price_cents"] == 4242
        assert probe.stats()["db_reads"] == 2
    finally:
        probe.purge()


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis + PostgreSQL")
@allure.story("Cache penetration")
@pytest.mark.integration
def test_negative_entry_keeps_repeated_missing_reads_off_the_database(
    sut_api_url: str,
    settings: Settings,
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
) -> None:
    missing_slug = f"{db_namespace.slug}-deleted"
    probe = CatalogCacheProbe(
        redis_url=str(settings.redis_url),
        workspace_slug=missing_slug,
    )
    probe.purge()
    try:
        with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
            first = client.get(f"/api/v1/workspaces/{missing_slug}/catalog")
            second = client.get(f"/api/v1/workspaces/{missing_slug}/catalog")
            third = client.get(f"/api/v1/workspaces/{missing_slug}/catalog")

        stats = probe.stats()
        absent = probe.absent_entry()
        allure.attach(
            "\n".join(
                [
                    f"cache states: {first.headers['X-Cache']}, "
                    f"{second.headers['X-Cache']}, {third.headers['X-Cache']}",
                    f"counters: {stats}",
                    f"negative entry TTL: {absent.ttl_seconds if absent else None}",
                ]
            ),
            name="negative cache evidence",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert [first.status_code, second.status_code, third.status_code] == [404] * 3
        assert stats["db_reads"] == 1
        assert stats["miss"] == 1
        assert stats["hit_negative"] == 2
        assert absent is not None
        assert absent.ttl_seconds <= settings.catalog_cache_negative_ttl_seconds
    finally:
        probe.purge()
