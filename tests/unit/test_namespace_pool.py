"""Unit tests for the lease-based namespace pool."""

from __future__ import annotations

import pytest
from qa_core.data_factories import NamespaceIdentity
from qa_core.db import UserRecord, WorkspaceRecord
from qa_core.resource_pools import NamespacePool


class FakeProvider:
    """In-memory stand-in for :class:`qa_core.data_factories.NamespaceFactory`."""

    def __init__(self, prefix: str = "qa-ns-") -> None:
        self._prefix = prefix
        self.created: list[NamespaceIdentity] = []
        self.reset_calls: list[str] = []
        self.purged: list[str] = []
        self.keep_runs: list[str | None] = []

    @property
    def prefix(self) -> str:
        return self._prefix

    def create(self, *, tag: str, with_viewer: bool = True) -> NamespaceIdentity:
        index = len(self.created) + 1
        slug = f"{self._prefix}fake-{tag}-{index}"
        workspace = WorkspaceRecord(
            workspace_id=index,
            slug=slug,
            name=f"Namespace {slug}",
        )
        identity = NamespaceIdentity(
            slug=slug,
            name=workspace.name,
            workspace=workspace,
            owner=UserRecord(
                user_id=index,
                workspace_id=index,
                email=f"owner@{slug}.example",
                display_name="Owner",
                role="owner",
                status="active",
            ),
            viewer=(
                UserRecord(
                    user_id=100 + index,
                    workspace_id=index,
                    email=f"viewer@{slug}.example",
                    display_name="Viewer",
                    role="viewer",
                    status="active",
                )
                if with_viewer
                else None
            ),
        )
        self.created.append(identity)
        return identity

    def reset(self, identity: NamespaceIdentity) -> int:
        self.reset_calls.append(identity.slug)
        return 0

    def purge(self, identity: NamespaceIdentity) -> int:
        self.purged.append(identity.slug)
        return 1

    def purge_stale(self, *, keep_run: str | None = None) -> list[str]:
        self.keep_runs.append(keep_run)
        return []


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def pool(provider: FakeProvider) -> NamespacePool:
    return NamespacePool(provider, worker_id="gw7", run_id="run42")


def test_first_lease_creates_a_namespace(
    pool: NamespacePool,
    provider: FakeProvider,
) -> None:
    with pool.lease("first") as lease:
        assert lease.slug == provider.created[0].slug
        assert lease.reused is False
        assert lease.worker_id == "gw7"
        assert lease.run_id == "run42"

    assert pool.stats["created"] == 1
    assert pool.stats["reused"] == 0
    assert pool.stats["released"] == 1


def test_released_namespace_is_reused_for_the_next_lease(
    pool: NamespacePool,
    provider: FakeProvider,
) -> None:
    with pool.lease("first") as first:
        first_slug = first.slug

    with pool.lease("second") as second:
        assert second.slug == first_slug
        assert second.reused is True
        assert second.tag == "second"

    assert len(provider.created) == 1
    assert pool.stats["reused"] == 1


def test_release_resets_the_namespace(
    pool: NamespacePool,
    provider: FakeProvider,
) -> None:
    with pool.lease("reset") as lease:
        slug = lease.slug

    assert provider.reset_calls == [slug]


def test_nested_lease_creates_a_second_namespace(
    pool: NamespacePool,
    provider: FakeProvider,
) -> None:
    with pool.lease("outer") as outer:
        with pool.lease("inner") as inner:
            assert inner.slug != outer.slug
            assert sorted(pool.active_slugs()) == sorted([outer.slug, inner.slug])

    assert len(provider.created) == 2


def test_releasing_an_outer_lease_replaces_the_idle_namespace(
    pool: NamespacePool,
    provider: FakeProvider,
) -> None:
    with pool.lease("outer") as outer:
        with pool.lease("inner") as inner:
            inner_slug = inner.slug
        outer_slug = outer.slug

    assert provider.purged == [inner_slug]
    with pool.lease("next") as next_lease:
        assert next_lease.slug == outer_slug


def test_close_purges_the_idle_namespace(
    pool: NamespacePool,
    provider: FakeProvider,
) -> None:
    with pool.lease("temporary") as lease:
        slug = lease.slug

    pool.close()

    assert provider.purged == [slug]
    assert pool.stats["idle"] == 0


def test_close_purges_leases_that_are_still_active(
    pool: NamespacePool,
    provider: FakeProvider,
) -> None:
    lease = pool.lease("leaked")
    with lease as active:
        slug = active.slug
        pool.close()
        assert slug in provider.purged


def test_active_slugs_track_the_current_lease(pool: NamespacePool) -> None:
    assert pool.active_slugs() == []
    with pool.lease("tracked") as lease:
        assert pool.active_slugs() == [lease.slug]
        assert pool.stats["active"] == 1
    assert pool.active_slugs() == []


def test_purge_stale_forwards_the_current_run(
    pool: NamespacePool,
    provider: FakeProvider,
) -> None:
    assert pool.purge_stale() == []
    assert provider.keep_runs == ["run42"]


def test_lease_label_contains_worker_and_run(pool: NamespacePool) -> None:
    with pool.lease("labelled") as lease:
        assert lease.label == f"{lease.slug} (worker=gw7, run=run42)"
