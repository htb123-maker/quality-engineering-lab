"""Normal API calls and the short-lived mobile fixture capability."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from qa_core.auth import AuthClient
from qa_core.contracts import CatalogItem, E2eFixtureSession

E2E_SESSION_PATH = "/api/v1/e2e/sessions"


@dataclass(frozen=True, slots=True)
class FixtureSession:
    """One server-issued capability and its bound catalog item."""

    session_id: str
    item: CatalogItem
    expires_in: int
    can_archive: bool


class FixtureSessionApi:
    """Create and consume fixture capabilities through the SUT API only."""

    def __init__(
        self,
        auth: AuthClient,
        *,
        base_url: str,
        client_id: str,
    ) -> None:
        self._auth = auth
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id

    def create(self, item_id: int) -> tuple[FixtureSession, str | None]:
        """Create one short-lived session and return its request ID."""

        response = self._auth.post(
            E2E_SESSION_PATH,
            json={"item_id": item_id},
            headers={"X-QA-Client-Id": self._client_id},
        )
        response.raise_for_status()
        session = E2eFixtureSession.model_validate(response.json())
        return (
            FixtureSession(
                session_id=session.session_id,
                item=session.item,
                expires_in=session.expires_in,
                can_archive=session.can_archive,
            ),
            response.headers.get("X-QA-Request-Id"),
        )

    def read(self, session_id: str) -> tuple[CatalogItem, str | None]:
        """Read the item through the same capability the mobile app uses."""

        with httpx.Client(base_url=self._base_url, timeout=10.0) as client:
            response = client.get(f"{E2E_SESSION_PATH}/{session_id}")
        response.raise_for_status()
        return (
            CatalogItem.model_validate(response.json()),
            response.headers.get("X-QA-Request-Id"),
        )

    def archive(self, session_id: str) -> tuple[CatalogItem, str | None]:
        """Archive the bound item through the fixture capability."""

        with httpx.Client(base_url=self._base_url, timeout=10.0) as client:
            response = client.post(f"{E2E_SESSION_PATH}/{session_id}/archive")
        response.raise_for_status()
        return (
            CatalogItem.model_validate(response.json()),
            response.headers.get("X-QA-Request-Id"),
        )
