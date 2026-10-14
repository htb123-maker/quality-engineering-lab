"""Seed isolated, disposable workspaces so parallel tests never share state."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from qa_core.db import (
    DEFAULT_NAMESPACE_PREFIX,
    DatabaseClient,
    UserRecord,
    WorkspaceRecord,
    WorkspaceRepository,
)

_TAG_PATTERN = re.compile(r"[^A-Za-z0-9-]+")


def _normalize_tag(tag: str) -> str:
    normalized = _TAG_PATTERN.sub("-", tag).strip("-")
    if not normalized:
        raise ValueError("tag must contain at least one letter or digit")
    return normalized.lower()


@dataclass(frozen=True)
class NamespaceIdentity:
    """One test-owned workspace with its owner and optional viewer."""

    slug: str
    name: str
    workspace: WorkspaceRecord
    owner: UserRecord
    viewer: UserRecord | None = None

    @property
    def workspace_id(self) -> int:
        """Return the numeric workspace id used by the SUT."""

        return self.workspace.workspace_id

    @property
    def owner_email(self) -> str:
        """Return the seeded owner email."""

        return self.owner.email

    @property
    def viewer_email(self) -> str | None:
        """Return the seeded viewer email when one was created."""

        return self.viewer.email if self.viewer is not None else None


class NamespaceFactory:
    """Create unique workspaces, users, and baseline catalog rows in PostgreSQL.

    Each namespace owns a unique slug, so two parallel pytest workers can hold
    independent catalogs in the same database. Every slug carries the factory
    prefix, which makes stale data from an interrupted run removable with one
    predicate.
    """

    def __init__(
        self,
        db: DatabaseClient,
        *,
        prefix: str = DEFAULT_NAMESPACE_PREFIX,
        run_token: str | None = None,
    ) -> None:
        self._repository = WorkspaceRepository(db, prefix=prefix)
        self._run_token = run_token or uuid4().hex[:8]

    @property
    def prefix(self) -> str:
        """Return the namespace slug prefix."""

        return self._repository.prefix

    @property
    def run_token(self) -> str:
        """Return the token that identifies this test run."""

        return self._run_token

    def new_slug(self, tag: str = "ns") -> str:
        """Return a unique, URL-safe workspace slug."""

        suffix = uuid4().hex[:8]
        return f"{self.prefix}{self._run_token}-{_normalize_tag(tag)}-{suffix}"

    def new_item_sku(self, tag: str = "ITEM") -> str:
        """Return a contract-valid SKU that is unique across the database."""

        return f"QA8-{_normalize_tag(tag).upper()}-{uuid4().hex[:8].upper()}"

    def create(
        self,
        *,
        tag: str = "ns",
        slug: str | None = None,
        name: str | None = None,
        items: int = 0,
        with_viewer: bool = True,
    ) -> NamespaceIdentity:
        """Seed one namespace and return the rows that were written."""

        if items < 0:
            raise ValueError("items must not be negative")

        resolved_slug = slug or self.new_slug(tag)
        if len(resolved_slug) > 60:
            raise ValueError("workspace slug must be at most 60 characters")

        workspace = self._repository.upsert_workspace(
            slug=resolved_slug,
            name=name or f"Namespace {resolved_slug}",
        )
        owner = self._repository.upsert_user(
            workspace_id=workspace.workspace_id,
            email=f"owner@{resolved_slug}.example",
            display_name="Namespace Owner",
            role="owner",
        )
        viewer = (
            self._repository.upsert_user(
                workspace_id=workspace.workspace_id,
                email=f"viewer@{resolved_slug}.example",
                display_name="Namespace Viewer",
                role="viewer",
            )
            if with_viewer
            else None
        )
        for index in range(items):
            self._repository.upsert_item(
                workspace_id=workspace.workspace_id,
                sku=self.new_item_sku(f"SEED{index + 1}"),
                name=f"Seeded item {index + 1}",
                price_cents=(index + 1) * 100,
            )

        return NamespaceIdentity(
            slug=workspace.slug,
            name=workspace.name,
            workspace=workspace,
            owner=owner,
            viewer=viewer,
        )

    def purge(self, identity: NamespaceIdentity) -> int:
        """Delete one namespace; re-running with a removed slug is a no-op."""

        return self._repository.delete_namespace(identity.slug)

    def reset(self, identity: NamespaceIdentity) -> int:
        """Delete a namespace's catalog items while keeping the workspace."""

        return self._repository.delete_workspace_items(identity.workspace_id)

    def run_prefix(self, run_token: str | None = None) -> str:
        """Return the slug prefix that identifies one run's namespaces."""

        return f"{self.prefix}{run_token or self._run_token}-"

    def purge_stale(self, *, keep_run: str | None = None) -> list[str]:
        """Delete namespaces from earlier runs, keeping the current run alive."""

        keep_prefix = self.run_prefix(keep_run) if keep_run is not None else None
        return self._repository.purge_stale_namespaces(keep_prefix=keep_prefix)

    def list_slugs(self, *, keep_run: str | None = None) -> list[str]:
        """List test-owned namespaces, optionally excluding the current run."""

        keep_prefix = self.run_prefix(keep_run) if keep_run is not None else None
        return self._repository.list_namespaces(keep_prefix=keep_prefix)

    def seed_counts(self) -> dict[str, int]:
        """Count the canonical seed rows that tests must never disturb."""

        return self._repository.seed_counts()

    def leftover_counts(self) -> dict[str, int]:
        """Count rows inside every test-owned namespace."""

        return self._repository.leftover_counts()

    def counts_for_run(self, run_token: str | None = None) -> dict[str, int]:
        """Count rows owned by one run, ignoring other workers' namespaces."""

        return self._repository.count_namespaces(self.run_prefix(run_token))
