"""Data-factory and PostgreSQL seeding tests for isolated namespaces."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory, NamespaceFactory, NamespaceIdentity
from qa_core.db import DatabaseClient, WorkspaceRepository

from tests.api.conftest import attach_json, owner_session

SEED_COUNTS = {"workspaces": 2, "users": 3, "items": 4}


@contextmanager
def _seeded(
    factory: NamespaceFactory,
    *,
    tag: str,
    items: int = 0,
    with_viewer: bool = True,
) -> Iterator[NamespaceIdentity]:
    identity = factory.create(tag=tag, items=items, with_viewer=with_viewer)
    try:
        yield identity
    finally:
        factory.purge(identity)


def _workspace_row(database: DatabaseClient, slug: str) -> dict[str, object] | None:
    return database.fetch_one(
        "SELECT id, slug, name FROM workspaces WHERE slug = %s",
        (slug,),
    )


def _user_rows(database: DatabaseClient, workspace_id: int) -> list[dict[str, object]]:
    return database.fetch_all(
        "SELECT email, role, status FROM users WHERE workspace_id = %s ORDER BY email",
        (workspace_id,),
    )


def _item_rows(database: DatabaseClient, workspace_id: int) -> list[dict[str, object]]:
    return database.fetch_all(
        "SELECT sku, name, price_cents, status FROM catalog_items"
        " WHERE workspace_id = %s ORDER BY sku",
        (workspace_id,),
    )


@pytest.mark.api
def test_factory_seeds_a_workspace_with_owner_and_viewer(
    namespace_factory: NamespaceFactory,
    database: DatabaseClient,
) -> None:
    with _seeded(namespace_factory, tag="factory") as identity:
        workspace = _workspace_row(database, identity.slug)
        users = _user_rows(database, identity.workspace_id)

    assert workspace is not None
    assert workspace["id"] == identity.workspace_id
    assert [user["role"] for user in users] == ["owner", "viewer"]
    assert [user["status"] for user in users] == ["active", "active"]
    assert identity.owner_email == f"owner@{identity.slug}.example"
    assert identity.viewer_email == f"viewer@{identity.slug}.example"
    attach_json("Seeded namespace", {"slug": identity.slug, "users": users})


@pytest.mark.api
def test_factory_can_omit_the_viewer(
    namespace_factory: NamespaceFactory,
    database: DatabaseClient,
) -> None:
    with _seeded(namespace_factory, tag="noviewer", with_viewer=False) as identity:
        users = _user_rows(database, identity.workspace_id)

    assert identity.viewer_email is None
    assert [user["role"] for user in users] == ["owner"]


@pytest.mark.api
def test_each_factory_call_creates_a_distinct_slug(
    namespace_factory: NamespaceFactory,
) -> None:
    with _seeded(namespace_factory, tag="unique") as first:
        with _seeded(namespace_factory, tag="unique") as second:
            assert first.slug != second.slug
            assert first.workspace_id != second.workspace_id


@pytest.mark.api
def test_slug_carries_the_prefix_and_run_token(
    namespace_factory: NamespaceFactory,
) -> None:
    with _seeded(namespace_factory, tag="naming") as identity:
        assert identity.slug.startswith(namespace_factory.run_prefix())


@pytest.mark.api
def test_factory_rejects_a_negative_item_count(
    namespace_factory: NamespaceFactory,
) -> None:
    with pytest.raises(ValueError, match="items must not be negative"):
        namespace_factory.create(tag="negative", items=-1)


@pytest.mark.api
def test_seeded_items_are_readable_through_the_api(
    namespace_factory: NamespaceFactory,
    database: DatabaseClient,
    settings: Settings,
) -> None:
    with _seeded(namespace_factory, tag="seed", items=3) as identity:
        rows = _item_rows(database, identity.workspace_id)
        with owner_session(identity.owner_email, settings) as auth:
            catalog = auth.get(f"/api/v1/workspaces/{identity.slug}/catalog")

    assert [row["status"] for row in rows] == ["active", "active", "active"]
    assert catalog.status_code == 200
    assert catalog.json()["count"] == 3
    attach_json("Seeded catalog", catalog.json())


@pytest.mark.api
def test_reseeding_the_same_slug_is_idempotent(
    namespace_factory: NamespaceFactory,
    database: DatabaseClient,
) -> None:
    with _seeded(namespace_factory, tag="idem", items=2) as identity:
        reseeded = namespace_factory.create(
            tag="idem",
            slug=identity.slug,
        )
        users = _user_rows(database, identity.workspace_id)
        items = _item_rows(database, identity.workspace_id)

    assert reseeded.workspace_id == identity.workspace_id
    assert len(users) == 2
    assert len(items) == 2


@pytest.mark.api
def test_upserting_the_same_sku_reuses_the_item_row(
    namespace_factory: NamespaceFactory,
    database: DatabaseClient,
) -> None:
    repository = WorkspaceRepository(database)
    with _seeded(namespace_factory, tag="upsert") as identity:
        sku = namespace_factory.new_item_sku("UPSERT")
        first_id = repository.upsert_item(
            workspace_id=identity.workspace_id,
            sku=sku,
            name="first name",
            price_cents=100,
        )
        second_id = repository.upsert_item(
            workspace_id=identity.workspace_id,
            sku=sku,
            name="second name",
            price_cents=200,
        )
        items = _item_rows(database, identity.workspace_id)

    assert first_id == second_id
    assert len(items) == 1
    assert items[0]["name"] == "second name"
    assert items[0]["price_cents"] == 200


@pytest.mark.api
def test_reset_clears_items_and_keeps_the_workspace(
    namespace_factory: NamespaceFactory,
    database: DatabaseClient,
) -> None:
    with _seeded(namespace_factory, tag="reset", items=2) as identity:
        removed = namespace_factory.reset(identity)
        workspace = _workspace_row(database, identity.slug)
        users = _user_rows(database, identity.workspace_id)
        items = _item_rows(database, identity.workspace_id)

    assert removed == 2
    assert workspace is not None
    assert len(users) == 2
    assert items == []


@pytest.mark.api
def test_purge_removes_the_workspace_and_dependent_rows(
    namespace_factory: NamespaceFactory,
    database: DatabaseClient,
) -> None:
    identity = namespace_factory.create(tag="purge", items=1)
    removed = namespace_factory.purge(identity)

    assert removed == 1
    assert _workspace_row(database, identity.slug) is None
    assert _user_rows(database, identity.workspace_id) == []
    assert _item_rows(database, identity.workspace_id) == []


@pytest.mark.api
def test_purge_is_idempotent_for_a_missing_namespace(
    namespace_factory: NamespaceFactory,
) -> None:
    identity = namespace_factory.create(tag="purge-twice")
    assert namespace_factory.purge(identity) == 1

    assert namespace_factory.purge(identity) == 0
    assert namespace_factory.purge(identity) == 0


@pytest.mark.api
def test_purge_stale_removes_earlier_runs_only(
    database: DatabaseClient,
    namespace_factory: NamespaceFactory,
) -> None:
    stale_factory = NamespaceFactory(database, run_token="stale123")
    stale = stale_factory.create(tag="stale")
    current = namespace_factory.create(tag="current")
    try:
        purged = namespace_factory.purge_stale(keep_run=namespace_factory.run_token)
        assert stale.slug in purged
        assert current.slug not in purged
        assert _workspace_row(database, stale.slug) is None
        assert _workspace_row(database, current.slug) is not None
    finally:
        namespace_factory.purge(current)


@pytest.mark.api
def test_factory_operations_leave_canonical_seed_rows_untouched(
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> None:
    before = namespace_factory.seed_counts()
    with _seeded(namespace_factory, tag="seedcheck", items=3) as identity:
        with owner_session(identity.owner_email, settings) as auth:
            created = CatalogApiFactory(
                auth=auth,
                workspace_slug=identity.slug,
                client_id="seedcheck",
            ).create()
            assert created.status_code == 201
        during = namespace_factory.seed_counts()
    after = namespace_factory.seed_counts()

    assert before == SEED_COUNTS
    assert during == SEED_COUNTS
    assert after == SEED_COUNTS


@pytest.mark.api
def test_run_scoped_counts_track_owned_rows(
    database: DatabaseClient,
) -> None:
    scoped_factory = NamespaceFactory(database, run_token="counts01")
    baseline = scoped_factory.counts_for_run()
    identity = scoped_factory.create(tag="leftover", items=2)
    try:
        during = scoped_factory.counts_for_run()
    finally:
        scoped_factory.purge(identity)
    after = scoped_factory.counts_for_run()

    assert baseline == {"workspaces": 0, "users": 0, "items": 0}
    assert during == {"workspaces": 1, "users": 2, "items": 2}
    assert after == baseline


@pytest.mark.api
def test_namespace_owner_session_matches_the_seeded_identity(
    namespace_factory: NamespaceFactory,
    settings: Settings,
) -> None:
    with _seeded(namespace_factory, tag="identity") as identity:
        with owner_session(identity.owner_email, settings) as auth:
            me = auth.get("/api/v1/auth/me")

    assert me.status_code == 200
    payload = me.json()
    assert payload["email"] == identity.owner_email
    assert payload["workspace_slug"] == identity.slug
    assert payload["workspace_id"] == identity.workspace_id
    assert payload["role"] == "owner"
    attach_json("Namespace identity", payload)
