"""Repositories that seed and clean test-owned PostgreSQL rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qa_core.db.client import DatabaseClient

DEFAULT_NAMESPACE_PREFIX = "qa-ns-"

# Canonical seed identity from apps/compose/postgres/init/002_seed.sql. The
# integrity checks count these rows by identity so isolated test namespaces can
# exist without making the seed check ambiguous.
SEED_WORKSPACE_SLUGS = ("atlas", "orbit")
SEED_USER_EMAILS = (
    "owner@atlas.example",
    "viewer@atlas.example",
    "admin@orbit.example",
)
SEED_ITEM_SKUS = ("LAB-001", "LAB-002", "LAB-003", "ORB-001")


@dataclass(frozen=True)
class WorkspaceRecord:
    """One workspace row."""

    workspace_id: int
    slug: str
    name: str


@dataclass(frozen=True)
class UserRecord:
    """One user row belonging to a workspace."""

    user_id: int
    workspace_id: int
    email: str
    display_name: str
    role: str
    status: str


def _workspace_from_row(row: dict[str, Any]) -> WorkspaceRecord:
    return WorkspaceRecord(
        workspace_id=int(row["id"]),
        slug=str(row["slug"]),
        name=str(row["name"]),
    )


def _user_from_row(row: dict[str, Any]) -> UserRecord:
    return UserRecord(
        user_id=int(row["id"]),
        workspace_id=int(row["workspace_id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"]),
        role=str(row["role"]),
        status=str(row["status"]),
    )


class WorkspaceRepository:
    """Seed workspaces, users, and catalog rows, then remove them again.

    Every write is an upsert keyed on the natural identifier, so re-running seed
    or cleanup is safe. Namespaces owned by tests all share
    :attr:`prefix`, which makes "remove everything this suite created" a single
    predicate instead of bookkeeping per test.
    """

    def __init__(
        self,
        db: DatabaseClient,
        *,
        prefix: str = DEFAULT_NAMESPACE_PREFIX,
    ) -> None:
        if not prefix or prefix.startswith("LAB-"):
            raise ValueError("namespace prefix must not be empty or seed data")
        self._db = db
        self._prefix = prefix

    @property
    def prefix(self) -> str:
        """Return the slug prefix that marks test-owned workspaces."""

        return self._prefix

    def upsert_workspace(self, *, slug: str, name: str) -> WorkspaceRecord:
        """Insert or rename one workspace and return its row."""

        row = self._db.fetch_one(
            """
            INSERT INTO workspaces (slug, name)
            VALUES (%s, %s)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING id, slug, name
            """,
            (slug, name),
        )
        if row is None:
            raise RuntimeError(f"workspace upsert returned no row for {slug!r}")
        return _workspace_from_row(row)

    def upsert_user(
        self,
        *,
        workspace_id: int,
        email: str,
        display_name: str,
        role: str,
        status: str = "active",
    ) -> UserRecord:
        """Insert or update one workspace user."""

        row = self._db.fetch_one(
            """
            INSERT INTO users (workspace_id, email, display_name, role, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (workspace_id, email) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    role = EXCLUDED.role,
                    status = EXCLUDED.status
            RETURNING id, workspace_id, email, display_name, role, status
            """,
            (workspace_id, email, display_name, role, status),
        )
        if row is None:
            raise RuntimeError(f"user upsert returned no row for {email!r}")
        return _user_from_row(row)

    def upsert_item(
        self,
        *,
        workspace_id: int,
        sku: str,
        name: str,
        price_cents: int,
        status: str = "active",
    ) -> int:
        """Insert or update one catalog item and return its id."""

        row = self._db.fetch_one(
            """
            INSERT INTO catalog_items
                (workspace_id, sku, name, price_cents, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (workspace_id, sku) DO UPDATE
                SET name = EXCLUDED.name,
                    price_cents = EXCLUDED.price_cents,
                    status = EXCLUDED.status
            RETURNING id
            """,
            (workspace_id, sku, name, price_cents, status),
        )
        if row is None:
            raise RuntimeError(f"catalog upsert returned no row for {sku!r}")
        return int(row["id"])

    def delete_namespace(self, slug: str) -> int:
        """Delete one test workspace and its dependent rows through the cascade."""

        return self._db.execute("DELETE FROM workspaces WHERE slug = %s", (slug,))

    def delete_workspace_items(self, workspace_id: int) -> int:
        """Delete every catalog item in one workspace without deleting the workspace."""

        return self._db.execute(
            "DELETE FROM catalog_items WHERE workspace_id = %s",
            (workspace_id,),
        )

    def list_namespaces(self, *, keep_prefix: str | None = None) -> list[str]:
        """List owned workspace slugs, optionally keeping one run out of scope."""

        sql = "SELECT slug FROM workspaces WHERE starts_with(slug, %s)"
        params: list[str] = [self._prefix]
        if keep_prefix is not None:
            sql += " AND NOT starts_with(slug, %s)"
            params.append(keep_prefix)
        sql += " ORDER BY slug"
        rows = self._db.fetch_all(sql, params)
        return [str(row["slug"]) for row in rows]

    def purge_stale_namespaces(self, *, keep_prefix: str | None = None) -> list[str]:
        """Delete owned workspaces except the kept run and return their slugs.

        Parallel workers of one run must not delete each other's live
        namespaces, so cleanup excludes every slug that starts with the current
        run's prefix.
        """

        sql = "DELETE FROM workspaces WHERE starts_with(slug, %s)"
        params: list[str] = [self._prefix]
        if keep_prefix is not None:
            sql += " AND NOT starts_with(slug, %s)"
            params.append(keep_prefix)
        sql += " RETURNING slug"
        rows = self._db.fetch_all(sql, params)
        return sorted(str(row["slug"]) for row in rows)

    def seed_counts(self) -> dict[str, int]:
        """Count canonical seed rows by identity, ignoring test namespaces."""

        row = self._db.fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM workspaces
                 WHERE slug = ANY(%s)) AS workspaces,
                (SELECT COUNT(*) FROM users u
                 JOIN workspaces w ON w.id = u.workspace_id
                 WHERE u.email = ANY(%s)) AS users,
                (SELECT COUNT(*) FROM catalog_items i
                 JOIN workspaces w ON w.id = i.workspace_id
                 WHERE i.sku = ANY(%s)) AS items
            """,
            (
                list(SEED_WORKSPACE_SLUGS),
                list(SEED_USER_EMAILS),
                list(SEED_ITEM_SKUS),
            ),
        )
        if row is None:
            raise RuntimeError("seed count query returned no row")
        return {name: int(row[name]) for name in ("workspaces", "users", "items")}

    def leftover_counts(self) -> dict[str, int]:
        """Count rows inside owned namespaces that should be gone at rest."""

        return self.count_namespaces(self._prefix)

    def count_namespaces(self, slug_prefix: str) -> dict[str, int]:
        """Count workspaces, users, and items under one slug prefix."""

        row = self._db.fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM workspaces
                 WHERE starts_with(slug, %s)) AS workspaces,
                (SELECT COUNT(*) FROM users u
                 JOIN workspaces w ON w.id = u.workspace_id
                 WHERE starts_with(w.slug, %s)) AS users,
                (SELECT COUNT(*) FROM catalog_items i
                 JOIN workspaces w ON w.id = i.workspace_id
                 WHERE starts_with(w.slug, %s)) AS items
            """,
            (slug_prefix, slug_prefix, slug_prefix),
        )
        if row is None:
            raise RuntimeError("namespace count query returned no row")
        return {name: int(row[name]) for name in ("workspaces", "users", "items")}
