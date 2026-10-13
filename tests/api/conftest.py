"""Fixtures for Week 7 catalog write, boundary, and state tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import uuid4

import allure
import httpx
import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings

ATLAS_SLUG = "atlas"
WEEK7_SKU_PREFIX = "QA7W"


def items_path(slug: str = ATLAS_SLUG) -> str:
    """Return the catalog items collection path for one workspace."""

    return f"/api/v1/workspaces/{slug}/catalog/items"


def item_path(item_id: int, slug: str = ATLAS_SLUG) -> str:
    """Return the catalog item path for one workspace item."""

    return f"{items_path(slug)}/{item_id}"


def unique_client_id(tag: str) -> str:
    """Return a per-test client id so the SUT rate limiter stays isolated."""

    return f"week7-{tag}-{uuid4().hex[:12]}"


def attach_json(name: str, payload: object) -> None:
    """Attach a JSON payload to the current Allure test."""

    allure.attach(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )


@dataclass
class CatalogItemFactory:
    """Create catalog items and delete them again during teardown."""

    auth: AuthClient
    client_id: str
    created: list[int] = field(default_factory=list)
    slug: str = ATLAS_SLUG

    def new_sku(self, tag: str = "ITEM") -> str:
        """Return a unique, contract-valid SKU."""

        return f"{WEEK7_SKU_PREFIX}-{tag}-{uuid4().hex[:8].upper()}"

    def create(
        self,
        *,
        sku: str | None = None,
        name: str = "Week 7 item",
        price_cents: int = 1500,
        idempotency_key: str | None = None,
    ) -> httpx.Response:
        """Create one catalog item and track the id when it succeeds."""

        headers = {"X-QA-Client-Id": self.client_id}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        response = self.auth.post(
            items_path(self.slug),
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
            item_path(item_id, self.slug),
            json={"status": status},
            headers={"X-QA-Client-Id": self.client_id},
        )

    def delete(self, item_id: int) -> httpx.Response:
        """Delete one catalog item by id."""

        return self.auth.request(
            "DELETE",
            item_path(item_id, self.slug),
            headers={"X-QA-Client-Id": self.client_id},
        )

    def catalog_items(self) -> list[dict[str, object]]:
        """Return the current catalog items for the workspace."""

        response = self.auth.get(f"/api/v1/workspaces/{self.slug}/catalog")
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


def _purge_leftover_items(auth: AuthClient) -> None:
    response = auth.get(f"/api/v1/workspaces/{ATLAS_SLUG}/catalog")
    if response.status_code != 200:
        return
    for item in response.json().get("items", []):
        if not isinstance(item, dict):
            continue
        sku = item.get("sku")
        if isinstance(sku, str) and sku.startswith(WEEK7_SKU_PREFIX):
            auth.request(
                "DELETE",
                item_path(int(item["id"])),
                headers={"X-QA-Client-Id": unique_client_id("purge")},
            )


@pytest.fixture(scope="session")
def owner_auth(sut_api_url: str, settings: Settings) -> Iterator[AuthClient]:
    """Return an authenticated atlas owner session for write tests."""

    del sut_api_url
    with AuthClient.from_settings(settings) as auth:
        auth.login(settings.auth_test_username, settings.auth_test_password)
        yield auth


@pytest.fixture(scope="session", autouse=True)
def purge_week7_leftovers(owner_auth: AuthClient) -> Iterator[None]:
    """Remove Week 7 leftovers before and after the API session."""

    _purge_leftover_items(owner_auth)
    yield
    _purge_leftover_items(owner_auth)


@pytest.fixture
def catalog_items(owner_auth: AuthClient) -> Iterator[CatalogItemFactory]:
    """Return a catalog item factory that cleans up after each test."""

    factory = CatalogItemFactory(
        auth=owner_auth,
        client_id=unique_client_id("factory"),
    )
    try:
        yield factory
    finally:
        factory.cleanup()
