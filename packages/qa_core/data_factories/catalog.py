"""Create and clean catalog items through the SUT API."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import uuid4

import httpx

from qa_core.auth import AuthClient

SKU_PREFIX = "QA8"
_TAG_PATTERN = re.compile(r"[^A-Za-z0-9]+")


def items_path(workspace_slug: str) -> str:
    """Return the catalog items collection path for one workspace."""

    return f"/api/v1/workspaces/{workspace_slug}/catalog/items"


def item_path(item_id: int, workspace_slug: str) -> str:
    """Return the catalog item path for one workspace item."""

    return f"{items_path(workspace_slug)}/{item_id}"


@dataclass
class CatalogApiFactory:
    """Create catalog items for one workspace and delete them during teardown."""

    auth: AuthClient
    workspace_slug: str
    client_id: str
    created: list[int] = field(default_factory=list)

    def new_sku(self, tag: str = "ITEM") -> str:
        """Return a unique, contract-valid SKU for this workspace."""

        normalized = _TAG_PATTERN.sub("", tag).upper() or "ITEM"
        return f"{SKU_PREFIX}-{normalized}-{uuid4().hex[:8].upper()}"

    def create(
        self,
        *,
        sku: str | None = None,
        name: str = "Week 8 item",
        price_cents: int = 1500,
        idempotency_key: str | None = None,
    ) -> httpx.Response:
        """Create one catalog item and track its id when it succeeds."""

        headers = {"X-QA-Client-Id": self.client_id}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        response = self.auth.post(
            items_path(self.workspace_slug),
            json={
                "sku": sku if sku is not None else self.new_sku(),
                "name": name,
                "price_cents": price_cents,
            },
            headers=headers,
        )
        if response.status_code == 201:
            created_id = int(response.json()["id"])
            if created_id not in self.created:
                self.created.append(created_id)
        return response

    def set_status(self, item_id: int, status: str) -> httpx.Response:
        """Request one catalog item state transition."""

        return self.auth.request(
            "PATCH",
            item_path(item_id, self.workspace_slug),
            json={"status": status},
            headers={"X-QA-Client-Id": self.client_id},
        )

    def delete(self, item_id: int) -> httpx.Response:
        """Delete one catalog item by id."""

        return self.auth.request(
            "DELETE",
            item_path(item_id, self.workspace_slug),
            headers={"X-QA-Client-Id": self.client_id},
        )

    def catalog_items(self) -> list[dict[str, object]]:
        """Return the current catalog items for the workspace."""

        response = self.auth.get(f"/api/v1/workspaces/{self.workspace_slug}/catalog")
        response.raise_for_status()
        items = response.json()["items"]
        return [item for item in items if isinstance(item, dict)]

    def cleanup(self) -> None:
        """Delete every tracked item, tolerating items already removed."""

        while self.created:
            item_id = self.created.pop()
            try:
                self.delete(item_id)
            except httpx.HTTPError:
                continue
