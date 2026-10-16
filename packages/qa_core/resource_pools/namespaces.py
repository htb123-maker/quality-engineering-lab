"""Hand out isolated namespaces to parallel pytest workers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from qa_core.cache import purge_catalog_cache, purge_idempotency_keys
from qa_core.data_factories import NamespaceIdentity
from qa_core.security import purge_write_budget


class NamespaceProvider(Protocol):
    """Interface the pool needs from a namespace factory."""

    @property
    def prefix(self) -> str:
        """Return the slug prefix that marks test-owned workspaces."""
        ...

    def create(self, *, tag: str, with_viewer: bool = True) -> NamespaceIdentity:
        """Seed one namespace."""
        ...

    def reset(self, identity: NamespaceIdentity) -> int:
        """Delete a namespace's catalog items."""
        ...

    def purge(self, identity: NamespaceIdentity) -> int:
        """Delete a namespace and its dependent rows."""
        ...

    def purge_stale(self, *, keep_run: str | None = None) -> list[str]:
        """Delete namespaces left behind by earlier runs."""
        ...


@dataclass(frozen=True)
class NamespaceLease:
    """One exclusive lease on a namespace."""

    identity: NamespaceIdentity
    worker_id: str
    run_id: str
    tag: str
    reused: bool

    @property
    def slug(self) -> str:
        """Return the leased workspace slug."""

        return self.identity.slug

    @property
    def workspace_id(self) -> int:
        """Return the leased workspace id."""

        return self.identity.workspace_id

    @property
    def owner_email(self) -> str:
        """Return the seeded owner email."""

        return self.identity.owner_email

    @property
    def viewer_email(self) -> str | None:
        """Return the seeded viewer email."""

        return self.identity.viewer_email

    @property
    def label(self) -> str:
        """Return a short label used in Allure attachments."""

        return f"{self.slug} (worker={self.worker_id}, run={self.run_id})"


class NamespacePool:
    """Reuse one namespace per worker and wipe it between leases.

    A worker keeps at most one idle namespace, so a long sequential run reuses
    the same workspace instead of paying a create/delete round trip per test.
    Extra nested leases are created on demand and destroyed on release, which
    keeps ``atlas`` and ``orbit`` untouched and gives every assertion a private
    catalog.
    """

    def __init__(
        self,
        provider: NamespaceProvider,
        *,
        worker_id: str = "local",
        run_id: str = "local",
        redis_url: str | None = None,
    ) -> None:
        self._provider = provider
        self._worker_id = worker_id
        self._run_id = run_id
        self._redis_url = redis_url
        self._idle: NamespaceIdentity | None = None
        self._active: dict[str, NamespaceLease] = {}
        self._created = 0
        self._reused = 0
        self._released = 0

    @property
    def worker_id(self) -> str:
        """Return the pytest worker this pool belongs to."""

        return self._worker_id

    @property
    def run_id(self) -> str:
        """Return the identifier shared by every worker in one test run."""

        return self._run_id

    @property
    def stats(self) -> dict[str, int]:
        """Return counters used by isolation tests and reports."""

        return {
            "created": self._created,
            "reused": self._reused,
            "released": self._released,
            "active": len(self._active),
            "idle": 1 if self._idle is not None else 0,
        }

    def active_slugs(self) -> list[str]:
        """Return the slugs currently leased by this pool."""

        return sorted(self._active)

    def purge_stale(self) -> list[str]:
        """Delete namespaces left behind by earlier interrupted runs.

        Namespaces created by other workers of the *current* run are kept, so a
        worker that starts later never deletes a peer's live workspace.
        """

        return self._provider.purge_stale(keep_run=self._run_id)

    @contextmanager
    def lease(self, tag: str = "case") -> Iterator[NamespaceLease]:
        """Yield an exclusive, empty namespace and reset it afterwards."""

        reused = self._idle is not None
        identity = self._idle or self._provider.create(tag=tag)
        self._idle = None
        if reused:
            self._reused += 1
        else:
            self._created += 1

        lease = NamespaceLease(
            identity=identity,
            worker_id=self._worker_id,
            run_id=self._run_id,
            tag=tag,
            reused=reused,
        )
        self._active[identity.slug] = lease
        try:
            yield lease
        finally:
            self._active.pop(identity.slug, None)
            self._release(identity)
            self._released += 1

    def close(self) -> None:
        """Delete the idle namespace and any namespace this pool still owns."""

        identities: list[NamespaceIdentity] = []
        if self._idle is not None:
            identities.append(self._idle)
            self._idle = None
        identities.extend(lease.identity for lease in self._active.values())
        self._active.clear()
        for identity in identities:
            self._purge_redis_state(identity)
            self._provider.purge(identity)

    def _release(self, identity: NamespaceIdentity) -> None:
        self._reset(identity)
        previous = self._idle
        self._idle = identity
        if previous is not None and previous.slug != identity.slug:
            self._provider.purge(previous)

    def _reset(self, identity: NamespaceIdentity) -> None:
        self._provider.reset(identity)
        self._purge_redis_state(identity)

    def _purge_redis_state(self, identity: NamespaceIdentity) -> None:
        """Drop the Redis keys whose lifetime is tied to one namespace.

        A lease promises a workspace with no state from the previous test, and
        from Week 10 on that includes the catalog cache and its counters. Week
        11 adds the write budgets of the workspace's users: the pool hands the
        same owner row to the next test, so a spent budget would otherwise leak
        into an unrelated test.
        """

        if self._redis_url is None:
            return
        purge_idempotency_keys(self._redis_url, identity.workspace_id)
        purge_catalog_cache(self._redis_url, identity.slug)
        user_ids = [identity.owner.user_id]
        if identity.viewer is not None:
            user_ids.append(identity.viewer.user_id)
        purge_write_budget(self._redis_url, user_ids)
