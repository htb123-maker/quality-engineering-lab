"""Provision and clean an isolated, idempotent performance dataset."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from qa_core.cache.catalog import purge_catalog_cache
from qa_core.db import DatabaseClient, WorkspaceRecord, WorkspaceRepository

PERFORMANCE_NAMESPACE_PREFIX = "qa-perf-"
_RUN_ID_PATTERN = re.compile(r"[^A-Za-z0-9-]+")
_ROLE = Literal["owner", "viewer"]


def normalize_run_id(run_id: str) -> str:
    """Return a path-safe token while rejecting an empty result."""

    normalized = _RUN_ID_PATTERN.sub("-", run_id).strip("-").lower()
    if not normalized:
        raise ValueError("run_id must contain at least one letter or digit")
    return normalized


def performance_workspace_slug(run_id: str) -> str:
    """Return the deterministic workspace slug for one performance experiment."""

    slug = f"{PERFORMANCE_NAMESPACE_PREFIX}{normalize_run_id(run_id)}"
    if len(slug) > 60:
        raise ValueError("performance workspace slug must be at most 60 characters")
    return slug


def load_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE lines without executing shell content."""

    if not path.is_file():
        raise FileNotFoundError(f"environment file not found: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip()
    return values


def setting_from_sources(
    name: str,
    *,
    explicit: str | None,
    env_file: dict[str, str],
    default: str | None = None,
) -> str:
    """Resolve an explicit CLI value, the process environment, then an env file."""

    value = explicit or os.getenv(name) or env_file.get(name) or default
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


class PerformanceAccount(BaseModel):
    """One account from the isolated performance data pool."""

    model_config = ConfigDict(frozen=True)

    email: str = Field(min_length=3, max_length=254)
    role: _ROLE


class PerformanceRuntimeData(BaseModel):
    """Runtime-only data consumed by the authenticated Locust journeys.

    The password is written only to a git-ignored runtime file. It must never
    appear in the weekly report or structured performance manifest.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    run_id: str
    workspace_slug: str
    password: str = Field(min_length=1)
    redis_url: str
    accounts: tuple[PerformanceAccount, ...] = Field(min_length=1)


class PerformanceDatasetManifest(BaseModel):
    """Non-secret description of one provisioned performance dataset."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    run_id: str
    workspace_slug: str
    workspace_id: int
    item_count: int = Field(ge=0)
    account_count: int = Field(ge=1)
    created_at: datetime
    metadata_path: str
    runtime_data_path: str


@dataclass(frozen=True)
class PerformanceDataset:
    """The runtime and metadata paths created for one experiment."""

    manifest: PerformanceDatasetManifest
    runtime: PerformanceRuntimeData
    metadata_path: Path
    runtime_data_path: Path


class PerformanceDataPool:
    """Create one deterministic workspace, its accounts, and catalog rows."""

    def __init__(
        self,
        db: DatabaseClient,
        *,
        redis_url: str,
        prefix: str = PERFORMANCE_NAMESPACE_PREFIX,
    ) -> None:
        self._db = db
        self._redis_url = redis_url
        self._repository = WorkspaceRepository(db, prefix=prefix)

    def provision(
        self,
        *,
        run_id: str,
        password: str,
        output_root: Path,
        item_count: int = 100,
        account_count: int = 16,
        workspace_slug: str | None = None,
    ) -> PerformanceDataset:
        """Create or reshape one performance dataset without creating duplicates."""

        if not password:
            raise ValueError("performance test password must not be empty")
        if item_count < 0:
            raise ValueError("item_count must not be negative")
        if account_count < 1:
            raise ValueError("account_count must be at least one")

        normalized_run_id = normalize_run_id(run_id)
        slug = workspace_slug or performance_workspace_slug(normalized_run_id)
        if not slug.startswith(self._repository.prefix):
            raise ValueError(
                f"performance workspace slug must start with {self._repository.prefix!r}"
            )
        if len(slug) > 60:
            raise ValueError("performance workspace slug must be at most 60 characters")

        workspace = self._repository.upsert_workspace(
            slug=slug,
            name=f"Performance dataset {normalized_run_id}",
        )
        accounts = self._accounts(slug, account_count)
        expected_emails = [account.email for account in accounts]
        self._db.execute(
            """
            DELETE FROM users
            WHERE workspace_id = %s AND NOT (email = ANY(%s))
            """,
            (workspace.workspace_id, expected_emails),
        )
        for account in accounts:
            self._repository.upsert_user(
                workspace_id=workspace.workspace_id,
                email=account.email,
                display_name=account.email.split("@", 1)[0],
                role=account.role,
            )

        self._repository.delete_workspace_items(workspace.workspace_id)
        for index in range(item_count):
            self._repository.upsert_item(
                workspace_id=workspace.workspace_id,
                sku=f"PERF-{index + 1:04d}",
                name=f"Performance item {index + 1}",
                price_cents=(index + 1) * 100,
            )

        run_dir = output_root / "data" / normalized_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = run_dir / "metadata.json"
        runtime_data_path = run_dir / "runtime.json"
        created_at = datetime.now(UTC)
        runtime = PerformanceRuntimeData(
            run_id=normalized_run_id,
            workspace_slug=slug,
            password=password,
            redis_url=self._redis_url,
            accounts=accounts,
        )
        manifest = PerformanceDatasetManifest(
            run_id=normalized_run_id,
            workspace_slug=slug,
            workspace_id=workspace.workspace_id,
            item_count=item_count,
            account_count=account_count,
            created_at=created_at,
            metadata_path=str(metadata_path),
            runtime_data_path=str(runtime_data_path),
        )
        _write_json(metadata_path, manifest.model_dump(mode="json"))
        _write_json(runtime_data_path, runtime.model_dump(mode="json"))
        try:
            runtime_data_path.chmod(0o600)
        except OSError:
            pass
        return PerformanceDataset(
            manifest=manifest,
            runtime=runtime,
            metadata_path=metadata_path,
            runtime_data_path=runtime_data_path,
        )

    def cleanup(
        self,
        *,
        workspace_slug: str,
    ) -> dict[str, int]:
        """Purge cache keys and database rows, then return post-cleanup counts."""

        if not workspace_slug.startswith(self._repository.prefix):
            raise ValueError(f"refusing to clean a non-performance workspace: {workspace_slug!r}")
        purge_catalog_cache(self._redis_url, workspace_slug)
        self._repository.delete_namespace(workspace_slug)
        return self._repository.count_namespaces(workspace_slug)

    def counts(self, *, workspace_slug: str) -> dict[str, int]:
        """Return workspace, user, and item counts for one dataset."""

        return self._repository.count_namespaces(workspace_slug)

    def _accounts(self, slug: str, account_count: int) -> tuple[PerformanceAccount, ...]:
        accounts: list[PerformanceAccount] = []
        for index in range(account_count):
            role: _ROLE = "owner" if index == 0 else "viewer"
            accounts.append(
                PerformanceAccount(
                    email=f"perf-{index + 1:02d}@{slug}.example",
                    role=role,
                )
            )
        return tuple(accounts)


def load_runtime_data(path: Path) -> PerformanceRuntimeData:
    """Load and validate the git-ignored Locust runtime data file."""

    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    return PerformanceRuntimeData.model_validate(payload)


def workspace_from_manifest(path: Path) -> WorkspaceRecord:
    """Read the non-secret workspace identity from a dataset manifest."""

    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    manifest = PerformanceDatasetManifest.model_validate(payload)
    return WorkspaceRecord(
        workspace_id=manifest.workspace_id,
        slug=manifest.workspace_slug,
        name=f"Performance dataset {manifest.run_id}",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
