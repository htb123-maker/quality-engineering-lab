"""Worker-level isolation tests for the namespace resource pool."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory, NamespaceFactory
from qa_core.resource_pools import NamespaceLease, NamespacePool

from tests.api.conftest import (
    attach_json,
    items_path,
    owner_session,
    run_id,
    unique_client_id,
    worker_id,
)


def _local_pool(
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> NamespacePool:
    return NamespacePool(
        namespace_factory,
        worker_id="isolation-test",
        run_id=namespace_factory.run_token,
        redis_url=str(settings.redis_url),
    )


@contextmanager
def _throwaway_namespace(
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> Iterator[tuple[str, AuthClient]]:
    """Seed a throwaway namespace and yield its slug with an owner session."""

    identity = namespace_factory.create(tag="parallel")
    try:
        with owner_session(identity.owner_email, settings) as auth:
            yield identity.slug, auth
    finally:
        namespace_factory.purge(identity)


@pytest.mark.api
def test_lease_reports_worker_and_run_labels(namespace: NamespaceLease) -> None:
    assert namespace.worker_id == worker_id()
    assert namespace.run_id == run_id()
    assert namespace.label == (
        f"{namespace.slug} (worker={worker_id()}, run={run_id()})"
    )


@pytest.mark.api
def test_nested_lease_uses_a_different_workspace(
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
) -> None:
    assert namespace.slug != peer_namespace.slug
    assert namespace.workspace_id != peer_namespace.workspace_id


@pytest.mark.api
def test_pool_reuses_and_resets_a_released_namespace(
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> None:
    pool = _local_pool(namespace_factory, settings)
    try:
        with pool.lease("first") as first:
            with owner_session(first.owner_email, settings) as auth:
                created = CatalogApiFactory(
                    auth=auth,
                    workspace_slug=first.slug,
                    client_id=unique_client_id("reuse"),
                ).create()
            assert created.status_code == 201
            first_slug = first.slug

        with pool.lease("second") as second:
            assert second.slug == first_slug
            assert second.reused is True
            with owner_session(second.owner_email, settings) as auth:
                catalog = auth.get(f"/api/v1/workspaces/{second.slug}/catalog")
            assert catalog.json()["count"] == 0
            attach_json("Reused namespace catalog", catalog.json())
    finally:
        pool.close()


@pytest.mark.api
def test_pool_close_purges_the_idle_namespace(
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> None:
    pool = _local_pool(namespace_factory, settings)
    with pool.lease("temporary") as lease:
        slug = lease.slug
    assert slug in namespace_factory.list_slugs()

    pool.close()

    assert slug not in namespace_factory.list_slugs()
    attach_json("Purged idle namespace", {"slug": slug})


@pytest.mark.api
def test_active_leases_are_visible_through_pool_stats(
    namespace_pool: NamespacePool,
    namespace: NamespaceLease,
) -> None:
    stats = namespace_pool.stats

    assert namespace_pool.active_slugs() == [namespace.slug]
    assert stats["active"] == 1
    assert stats["created"] + stats["reused"] >= stats["released"] + 1


@pytest.mark.api
def test_purge_stale_keeps_the_current_run(
    namespace_pool: NamespacePool,
    namespace: NamespaceLease,
) -> None:
    purged = namespace_pool.purge_stale()

    assert namespace.slug not in purged
    assert namespace.slug in namespace_pool.active_slugs()


@pytest.mark.api
def test_run_scoped_counts_start_from_zero_for_a_new_run(
    namespace_factory: NamespaceFactory,
) -> None:
    assert namespace_factory.counts_for_run("no-such-run") == {
        "workspaces": 0,
        "users": 0,
        "items": 0,
    }


@pytest.mark.api
def test_isolated_writes_do_not_change_the_canonical_seed(
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> None:
    before = namespace_factory.seed_counts()

    with _throwaway_namespace(namespace_factory, settings) as (slug, auth):
        created = auth.post(
            items_path(slug),
            json={"sku": "QA8-PARALLEL-001", "name": "Parallel item", "price_cents": 100},
            headers={"X-QA-Client-Id": unique_client_id("parallel")},
        )
        assert created.status_code == 201

    assert namespace_factory.seed_counts() == before
