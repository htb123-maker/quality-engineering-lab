"""Cache-aside behavior of catalog reads, checked against the real Redis keys."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from uuid import uuid4

import allure
import httpx
import pytest
from qa_core.auth import AuthClient
from qa_core.cache import CatalogCacheProbe
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory
from qa_core.jobs import JobClient, job_path
from qa_core.resource_pools import NamespaceLease

from tests.api.conftest import attach_json, owner_session, unique_client_id


def catalog_path(slug: str) -> str:
    """Return the read path of one workspace catalog."""

    return f"/api/v1/workspaces/{slug}/catalog"


def read_catalog(client: httpx.Client, slug: str) -> httpx.Response:
    """Read a catalog through the plain HTTP client."""

    return client.get(catalog_path(slug))


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis cache")
@allure.story("Cache aside")
@pytest.mark.api
def test_first_read_warms_the_cache_and_the_second_read_hits_it(
    sut_api_url: str,
    settings: Settings,
    namespace: NamespaceLease,
    catalog_cache: CatalogCacheProbe,
) -> None:
    with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
        first = read_catalog(client, namespace.slug)
        first_ttl = int(first.headers["X-Cache-TTL"])
        second = read_catalog(client, namespace.slug)
        second_ttl = int(second.headers["X-Cache-TTL"])

    entry = catalog_cache.entry()
    stats = catalog_cache.stats()
    attach_json(
        "cache evidence",
        {
            "first": first.headers.get("X-Cache"),
            "second": second.headers.get("X-Cache"),
            "ttl_first": first_ttl,
            "ttl_second": second_ttl,
            "entry_ttl": entry.ttl_seconds if entry else None,
            "stats": stats,
        },
    )

    assert first.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    assert second.status_code == 200
    assert second.headers["X-Cache"] == "HIT"

    assert entry is not None
    assert entry.payload == first.json()
    assert 0 < entry.ttl_seconds <= settings.catalog_cache_ttl_seconds
    assert 0 <= second_ttl <= first_ttl <= settings.catalog_cache_ttl_seconds

    assert stats["miss"] == 1
    assert stats["hit"] == 1
    assert stats["db_reads"] == 1


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis cache")
@allure.story("Cache expiry")
@pytest.mark.api
def test_expired_entry_sends_the_next_read_back_to_postgresql(
    sut_api_url: str,
    namespace: NamespaceLease,
    catalog_cache: CatalogCacheProbe,
) -> None:
    with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
        warm = read_catalog(client, namespace.slug)
        assert warm.headers["X-Cache"] == "MISS"

        entry = catalog_cache.entry()
        assert entry is not None
        assert catalog_cache.expire_soon(entry.key, seconds=1)
        assert catalog_cache.wait_until_expired(entry.key)

        after_expiry = read_catalog(client, namespace.slug)

    stats = catalog_cache.stats()
    attach_json(
        "expiry evidence",
        {"stats": stats, "after_expiry": after_expiry.headers.get("X-Cache")},
    )

    assert after_expiry.status_code == 200
    assert after_expiry.headers["X-Cache"] == "MISS"
    assert after_expiry.json() == warm.json()
    assert stats["miss"] == 2
    assert stats["db_reads"] == 2
    assert catalog_cache.entry() is not None


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis cache")
@allure.story("Invalidation")
@pytest.mark.api
def test_api_write_drops_the_cached_catalog(
    sut_api_url: str,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
    catalog_cache: CatalogCacheProbe,
) -> None:
    with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
        warm = read_catalog(client, namespace.slug)
        assert warm.headers["X-Cache"] == "MISS"
        assert catalog_cache.entry() is not None

        sku = catalog_items.new_sku("CACHE")
        created = catalog_items.create(sku=sku, name="Invalidator", price_cents=999)
        key_gone = catalog_cache.entry() is None
        reread = read_catalog(client, namespace.slug)

    stats = catalog_cache.stats()
    entry = catalog_cache.entry()
    attach_json(
        "invalidation evidence",
        {
            "created": created.status_code,
            "key_gone": key_gone,
            "reread": reread.headers.get("X-Cache"),
            "stats": stats,
        },
    )

    assert created.status_code == 201
    assert key_gone, "a write must not leave the previous catalog in Redis"
    assert reread.headers["X-Cache"] == "MISS"
    skus = {item["sku"] for item in reread.json()["items"]}
    assert sku in skus
    assert stats["invalidations"] >= 1
    assert entry is not None
    assert reread.json() == entry.payload


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis cache")
@allure.story("Cache penetration")
@pytest.mark.api
def test_repeated_unknown_workspace_reads_hit_the_negative_cache(
    sut_api_url: str,
    settings: Settings,
    catalog_cache: CatalogCacheProbe,
) -> None:
    missing_slug = f"qa-ns-missing-{uuid4().hex[:8]}"
    probe = CatalogCacheProbe(
        redis_url=str(settings.redis_url),
        workspace_slug=missing_slug,
    )
    probe.purge()
    try:
        with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
            first = read_catalog(client, missing_slug)
            second = read_catalog(client, missing_slug)
            third = read_catalog(client, missing_slug)

        stats = probe.stats()
        absent = probe.absent_entry()
        attach_json(
            "penetration evidence",
            {
                "states": [
                    first.headers.get("X-Cache"),
                    second.headers.get("X-Cache"),
                    third.headers.get("X-Cache"),
                ],
                "absent_ttl": absent.ttl_seconds if absent else None,
                "stats": stats,
            },
        )

        assert [first.status_code, second.status_code, third.status_code] == [
            404,
            404,
            404,
        ]
        assert first.headers["X-Cache"] == "MISS"
        assert second.headers["X-Cache"] == "HIT-NEGATIVE"
        assert third.headers["X-Cache"] == "HIT-NEGATIVE"
        assert stats["db_reads"] == 1, "only the first miss may reach PostgreSQL"
        assert stats["hit_negative"] == 2
        assert absent is not None
        assert absent.payload["error"] == "workspace_not_found"
        assert 0 < absent.ttl_seconds <= settings.catalog_cache_negative_ttl_seconds
    finally:
        probe.purge()


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis cache")
@allure.story("Async refresh")
@pytest.mark.api
def test_cache_refresh_job_warms_the_cache_without_a_read(
    sut_api_url: str,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
    job_client: JobClient,
    catalog_cache: CatalogCacheProbe,
) -> None:
    created = catalog_items.create(name="Warm me", price_cents=250)
    assert created.status_code == 201
    catalog_cache.purge()
    assert catalog_cache.entry() is None

    before = job_client.queue_stats()
    accepted = job_client.refresh_catalog_cache(
        namespace.slug,
        client_id=unique_client_id("refresh"),
    )
    snapshot = job_client.wait(accepted.job_id)
    after = job_client.queue_stats()

    entry = catalog_cache.entry()
    attach_json(
        "refresh evidence",
        {
            "job_id": accepted.job_id,
            "location": accepted.location,
            "status": snapshot.status,
            "result": snapshot.result,
            "started_at": snapshot.started_at,
            "finished_at": snapshot.finished_at,
            "processed_before": before.processed,
            "processed_after": after.processed,
        },
    )

    assert accepted.status == "queued"
    assert accepted.location == job_path(accepted.job_id)
    assert snapshot.status == "succeeded"
    assert snapshot.error is None
    assert snapshot.started_at is not None
    assert snapshot.finished_at is not None
    assert snapshot.result is not None
    assert snapshot.result["workspace_slug"] == namespace.slug
    assert after.processed == before.processed + 1
    assert after.queued == 0

    assert entry is not None, "the worker, not the caller, warms the cache"
    assert entry.payload["count"] == len(entry.payload["items"])
    assert entry.payload["count"] >= 1

    with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
        served = read_catalog(client, namespace.slug)
    assert served.headers["X-Cache"] == "HIT"
    assert served.json() == entry.payload


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis cache")
@allure.story("Job isolation")
@pytest.mark.api
def test_job_records_are_only_readable_by_their_workspace(
    sut_api_url: str,
    settings: Settings,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
    job_client: JobClient,
) -> None:
    accepted = job_client.refresh_catalog_cache(namespace.slug)
    job_client.wait(accepted.job_id)

    with httpx.Client(base_url=sut_api_url, timeout=5.0) as anonymous:
        unauthenticated = anonymous.get(job_path(accepted.job_id))

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        foreign = peer_auth.get(job_path(accepted.job_id))
        unknown = peer_auth.get(job_path(uuid4().hex))

    attach_json(
        "job isolation evidence",
        {
            "anonymous": [unauthenticated.status_code, unauthenticated.json()],
            "foreign": [foreign.status_code, foreign.json()],
            "unknown": [unknown.status_code, unknown.json()],
        },
    )

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"] == "authentication_required"
    assert foreign.status_code == 403
    assert foreign.json()["error"] == "permission_denied"
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "job_not_found"


@allure.epic("Quality Engineering Lab")
@allure.feature("Redis cache")
@allure.story("Job isolation")
@pytest.mark.api
def test_forbidden_refresh_never_queues_a_job(
    namespace: NamespaceLease,
    viewer_auth: AuthClient,
    job_client: JobClient,
) -> None:
    before = job_client.queue_stats()

    response = viewer_auth.post(
        f"/api/v1/workspaces/{namespace.slug}/catalog/cache/refresh",
        json={},
        headers={"X-QA-Client-Id": unique_client_id("viewer")},
    )
    after = job_client.queue_stats()

    assert response.status_code == 403
    assert response.json()["error"] == "permission_denied"
    assert after.queued == before.queued
    assert after.delayed == before.delayed
