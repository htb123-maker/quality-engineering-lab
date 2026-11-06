"""Concrete ports and inventory loading for Week 23 cross-layer tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml
from qa_core.data_factories import CatalogApiFactory
from qa_core.e2e import (
    CatalogItemState,
    E2eContext,
    E2eSetup,
    FixtureSessionApi,
)
from qa_core.mobile.fixture_scenarios import (
    CATALOG_ARCHIVE_SCENARIO,
    CatalogInteractionState,
)
from qa_core.mobile.platforms import CatalogSnapshot, PlatformAdapter

from tests.cross_platform.support import run_with_evidence


@dataclass(frozen=True, slots=True)
class E2eCase:
    """One executable case from the Week 23 inventory."""

    test_id: str
    role: str
    item_state: str
    session_state: str
    action: str
    expected_ui: str
    expected_api: str
    warm_cache: bool = False
    request_id_required: bool = False


def load_cases(path: Path) -> tuple[E2eCase, ...]:
    """Load and validate the committed E2E inventory."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("E2E inventory must be version 1")
    raw_cases = payload.get("tests")
    if not isinstance(raw_cases, list):
        raise ValueError("E2E inventory tests must be a list")
    cases = tuple(_case(raw) for raw in raw_cases)
    test_ids = [case.test_id for case in cases]
    if len(test_ids) != len(set(test_ids)):
        raise ValueError("E2E inventory Test IDs must be unique")
    if len(cases) < 30:
        raise ValueError("Week 23 E2E inventory must contain at least 30 cases")
    return cases


def _case(raw: Any) -> E2eCase:
    if not isinstance(raw, dict):
        raise ValueError("each E2E inventory case must be an object")
    values = {
        key: raw.get(key, "")
        for key in (
            "id",
            "role",
            "item_state",
            "session_state",
            "action",
            "expected_ui",
            "expected_api",
        )
    }
    if not all(isinstance(value, str) and value for value in values.values()):
        raise ValueError("E2E inventory fields must be non-empty strings")
    case = E2eCase(
        test_id=values["id"],
        role=values["role"],
        item_state=values["item_state"],
        session_state=values["session_state"],
        action=values["action"],
        expected_ui=values["expected_ui"],
        expected_api=values["expected_api"],
        warm_cache=bool(raw.get("warm_cache", False)),
        request_id_required=bool(raw.get("request_id_required", False)),
    )
    if case.role not in {"owner", "admin", "member", "viewer"}:
        raise ValueError(f"{case.test_id}: unsupported role")
    if case.item_state not in {"active", "archived", "deleted"}:
        raise ValueError(f"{case.test_id}: unsupported item state")
    if case.session_state not in {"valid", "invalid", "expired"}:
        raise ValueError(f"{case.test_id}: unsupported session state")
    if case.action not in {"read", "archive", "repeat-archive"}:
        raise ValueError(f"{case.test_id}: unsupported action")
    return case


class CatalogSetupPort:
    """Create the item and short-lived fixture session through real APIs."""

    def __init__(
        self,
        *,
        factory: CatalogApiFactory,
        fixture_api: FixtureSessionApi,
        case: E2eCase,
        mobile_base_url: str,
        redis_url: str,
        settings_client_id: str,
    ) -> None:
        self._factory = factory
        self._fixture_api = fixture_api
        self._case = case
        self._mobile_base_url = mobile_base_url
        self._redis_url = redis_url
        self._client_id = settings_client_id
        self._prepared: E2eSetup | None = None

    def prepare(self, context: E2eContext) -> E2eSetup:
        if self._prepared is not None:
            return self._prepared
        response = self._factory.create(
            name=f"Cross-layer {self._case.test_id}",
            price_cents=1500,
        )
        if response.status_code != 201:
            raise RuntimeError(
                f"catalog setup returned HTTP {response.status_code}: {response.text}"
            )
        item_id = int(response.json()["id"])
        item_name = str(response.json()["name"])
        if self._case.item_state == "archived":
            archived = self._factory.set_status(item_id, "archived")
            if archived.status_code != 200:
                raise RuntimeError(
                    f"archiving setup item returned HTTP {archived.status_code}"
                )

        session_id = ""
        api_request_id = response.headers.get("X-QA-Request-Id")
        can_archive = self._case.role != "viewer"
        if self._case.session_state != "invalid":
            session, api_request_id = self._fixture_api.create(item_id)
            session_id = session.session_id
            can_archive = session.can_archive
            if self._case.session_state == "expired":
                self._discard_session(session_id)

        if self._case.item_state == "deleted":
            deleted = self._factory.delete(item_id)
            if deleted.status_code != 204:
                raise RuntimeError(
                    f"deleting setup item returned HTTP {deleted.status_code}"
                )
        if self._case.warm_cache:
            warm = self._factory.auth.get(
                f"/api/v1/workspaces/{self._factory.workspace_slug}/catalog"
            )
            warm.raise_for_status()

        prepared = E2eSetup(
            context=context,
            workspace_slug=self._factory.workspace_slug,
            item_id=item_id,
            item_name=item_name,
            fixture_session_id=session_id or "x" * 43,
            mobile_base_url=self._mobile_base_url,
            api_request_id=api_request_id,
            can_archive=can_archive,
        )
        self._prepared = prepared
        return prepared

    def cleanup(self, setup: E2eSetup) -> None:
        del setup

    def _discard_session(self, session_id: str) -> None:
        import redis

        client = redis.Redis.from_url(self._redis_url, decode_responses=True)
        try:
            client.delete(f"e2e:fixture-session:{session_id}")
        finally:
            client.close()


class CatalogMobilePort:
    """Run the real mobile read/archive path for one case."""

    def __init__(self, adapter: PlatformAdapter, case: E2eCase) -> None:
        self._adapter = adapter
        self._case = case

    def run(self, setup: E2eSetup) -> CatalogSnapshot:
        initial = self._adapter.catalog.open(
            base_url=setup.mobile_base_url,
            session_id=setup.fixture_session_id,
        )
        if self._case.action == "read":
            return initial
        if initial.status == "error":
            return initial
        if self._case.action == "repeat-archive" and initial.status == "archived":
            return initial
        return run_with_evidence(
            CATALOG_ARCHIVE_SCENARIO,
            self._adapter,
            CatalogInteractionState(
                base_url=setup.mobile_base_url,
                session_id=setup.fixture_session_id,
                expected_name=setup.item_name,
                initial=initial,
            ),
        ).archived or initial


class CatalogVerificationPort:
    """Verify final state through the normal authenticated API."""

    def __init__(self, factory: CatalogApiFactory) -> None:
        self._factory = factory

    def verify(self, setup: E2eSetup) -> CatalogItemState:
        response = self._factory.auth.get(
            f"/api/v1/workspaces/{setup.workspace_slug}/catalog/items/{setup.item_id}"
        )
        response.raise_for_status()
        payload = response.json()
        return CatalogItemState(
            item_id=int(payload["id"]),
            name=str(payload["name"]),
            status=str(payload["status"]),
            request_id=response.headers.get("X-QA-Request-Id"),
        )


def catalog_item_response(
    factory: CatalogApiFactory,
    item_id: int,
) -> httpx.Response:
    """Return one item through the normal requiring-authentication API."""

    return factory.auth.get(
        f"/api/v1/workspaces/{factory.workspace_slug}/catalog/items/{item_id}"
    )
