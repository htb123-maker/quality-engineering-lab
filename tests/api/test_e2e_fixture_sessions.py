"""Short-lived mobile fixture session contracts against the real SUT."""

from __future__ import annotations

import httpx
import pytest
from qa_core.auth import AuthClient
from qa_core.data_factories import CatalogApiFactory


def _create_session(
    auth: AuthClient,
    *,
    item_id: int,
) -> httpx.Response:
    return auth.post(
        "/api/v1/e2e/sessions",
        json={"item_id": item_id},
        headers={"X-QA-Client-Id": f"week23-session-{item_id}"},
    )


@pytest.mark.api
def test_fixture_session_reads_and_archives_an_api_created_item(
    catalog_items: CatalogApiFactory,
    sut_api_url: str,
) -> None:
    created = catalog_items.create(name="API-backed mobile item")
    assert created.status_code == 201
    item_id = int(created.json()["id"])

    session_response = _create_session(catalog_items.auth, item_id=item_id)
    assert session_response.status_code == 201
    session = session_response.json()
    session_id = str(session["session_id"])
    assert session["item"]["id"] == item_id
    assert session["can_archive"] is True
    assert session_response.headers["X-QA-Request-Id"]

    with httpx.Client(base_url=sut_api_url, timeout=5.0) as public:
        read = public.get(f"/api/v1/e2e/sessions/{session_id}")
        archived = public.post(f"/api/v1/e2e/sessions/{session_id}/archive")

    assert read.status_code == 200
    assert read.json()["status"] == "active"
    assert read.headers["X-QA-Request-Id"]
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.headers["X-QA-Request-Id"]
    items = catalog_items.catalog_items()
    assert [item["status"] for item in items if item["id"] == item_id] == [
        "archived"
    ]


@pytest.mark.api
def test_viewer_fixture_session_is_read_only(
    catalog_items: CatalogApiFactory,
    viewer_auth: AuthClient,
    sut_api_url: str,
) -> None:
    created = catalog_items.create(name="Viewer read-only item")
    assert created.status_code == 201
    item_id = int(created.json()["id"])

    session_response = _create_session(viewer_auth, item_id=item_id)
    assert session_response.status_code == 201
    session = session_response.json()
    assert session["can_archive"] is False
    session_id = str(session["session_id"])

    with httpx.Client(base_url=sut_api_url, timeout=5.0) as public:
        read = public.get(f"/api/v1/e2e/sessions/{session_id}")
        denied = public.post(f"/api/v1/e2e/sessions/{session_id}/archive")

    assert read.status_code == 200
    assert read.json()["status"] == "active"
    assert denied.status_code == 403
    assert denied.json()["error"] == "permission_denied"
    items = catalog_items.catalog_items()
    assert [item["status"] for item in items if item["id"] == item_id] == [
        "active"
    ]


@pytest.mark.api
def test_fixture_session_stops_working_after_item_delete(
    catalog_items: CatalogApiFactory,
    sut_api_url: str,
) -> None:
    created = catalog_items.create(name="Deleted after session")
    assert created.status_code == 201
    item_id = int(created.json()["id"])
    session_response = _create_session(catalog_items.auth, item_id=item_id)
    assert session_response.status_code == 201
    session_id = str(session_response.json()["session_id"])
    assert catalog_items.delete(item_id).status_code == 204

    with httpx.Client(base_url=sut_api_url, timeout=5.0) as public:
        read = public.get(f"/api/v1/e2e/sessions/{session_id}")
        archive = public.post(f"/api/v1/e2e/sessions/{session_id}/archive")

    assert read.status_code == 404
    assert read.json()["error"] == "fixture_session_not_found"
    assert archive.status_code == 404
    assert archive.json()["error"] == "fixture_session_not_found"


@pytest.mark.api
def test_fixture_session_rejects_a_second_archive(
    catalog_items: CatalogApiFactory,
    sut_api_url: str,
) -> None:
    created = catalog_items.create(name="Repeated archive item")
    assert created.status_code == 201
    item_id = int(created.json()["id"])
    session_response = _create_session(catalog_items.auth, item_id=item_id)
    assert session_response.status_code == 201
    session_id = str(session_response.json()["session_id"])

    with httpx.Client(base_url=sut_api_url, timeout=5.0) as public:
        first = public.post(f"/api/v1/e2e/sessions/{session_id}/archive")
        second = public.post(f"/api/v1/e2e/sessions/{session_id}/archive")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"] == "invalid_state_transition"
    items = catalog_items.catalog_items()
    assert [item["status"] for item in items if item["id"] == item_id] == [
        "archived"
    ]
