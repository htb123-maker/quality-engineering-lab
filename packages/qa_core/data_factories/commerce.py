"""Drive the real commerce API with isolated test data and idempotency keys."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import httpx

from qa_core.auth import AuthClient


def commerce_base_path(workspace_slug: str) -> str:
    """Return the workspace-scoped commerce collection path."""

    return f"/api/v1/workspaces/{workspace_slug}/commerce"


def inventory_path(workspace_slug: str, item_id: int | None = None) -> str:
    """Return the inventory collection or one item's inventory path."""

    base = f"{commerce_base_path(workspace_slug)}/inventory"
    return base if item_id is None else f"{base}/{item_id}"


def orders_path(workspace_slug: str, order_id: int | None = None) -> str:
    """Return the order collection or one order's path."""

    base = f"{commerce_base_path(workspace_slug)}/orders"
    return base if order_id is None else f"{base}/{order_id}"


@dataclass(slots=True)
class CommerceApiFactory:
    """Execute commerce writes through the authenticated SUT."""

    auth: AuthClient
    workspace_slug: str
    client_id: str

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"X-QA-Client-Id": self.client_id}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def set_inventory(self, item_id: int, on_hand: int) -> httpx.Response:
        """Set absolute on-hand stock through the real inventory endpoint."""

        return self.auth.post(
            inventory_path(self.workspace_slug),
            json={"item_id": item_id, "on_hand": on_hand},
            headers=self._headers(),
        )

    def inventory(self, item_id: int) -> httpx.Response:
        """Read current on-hand and reserved inventory."""

        return self.auth.get(inventory_path(self.workspace_slug, item_id))

    def create_order(
        self,
        item_id: int,
        *,
        quantity: int = 1,
        idempotency_key: str | None = None,
    ) -> httpx.Response:
        """Create one order using a unique key unless the caller supplies one."""

        return self.auth.post(
            orders_path(self.workspace_slug),
            json={"item_id": item_id, "quantity": quantity},
            headers=self._headers(idempotency_key or uuid4().hex),
        )

    def order(self, order_id: int) -> httpx.Response:
        """Read one order through normal authenticated API semantics."""

        return self.auth.get(orders_path(self.workspace_slug, order_id))

    def pay(
        self,
        order_id: int,
        *,
        amount_cents: int | None = None,
        idempotency_key: str | None = None,
    ) -> httpx.Response:
        """Pay an order with an idempotency key."""

        payload: dict[str, object] = {}
        if amount_cents is not None:
            payload["amount_cents"] = amount_cents
        return self.auth.post(
            f"{orders_path(self.workspace_slug, order_id)}/payments",
            json=payload,
            headers=self._headers(idempotency_key or uuid4().hex),
        )

    def fulfill(self, order_id: int) -> httpx.Response:
        """Consume the reservation and fulfill a paid order."""

        return self.auth.post(
            f"{orders_path(self.workspace_slug, order_id)}/fulfill",
            json={},
            headers=self._headers(),
        )

    def cancel(self, order_id: int) -> httpx.Response:
        """Cancel an unpaid order and release its reservation."""

        return self.auth.post(
            f"{orders_path(self.workspace_slug, order_id)}/cancel",
            json={},
            headers=self._headers(),
        )

    def refund(self, order_id: int) -> httpx.Response:
        """Refund a paid or fulfilled order through the SUT."""

        return self.auth.post(
            f"{orders_path(self.workspace_slug, order_id)}/refund",
            json={},
            headers=self._headers(),
        )
