"""WebSocket push delivery, verified against real API writes and jobs."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import time

import allure
import httpx
import pytest
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory
from qa_core.events import WebSocketConnection, WebSocketHandshakeError, events_url
from qa_core.jobs import JobClient
from qa_core.resource_pools import NamespaceLease

from tests.api.conftest import (
    attach_json,
    connect_event_stream,
    owner_session,
    unique_client_id,
)


@allure.epic("Quality Engineering Lab")
@allure.feature("Event stream")
@allure.story("Push delivery")
@pytest.mark.api
def test_event_stream_pushes_catalog_writes_in_sequence(
    sut_api_url: str,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
    owner_access_token: str,
) -> None:
    sku = catalog_items.new_sku("STREAM")

    with connect_event_stream(sut_api_url, namespace.slug, owner_access_token) as stream:
        created = catalog_items.create(sku=sku, name="Pushed item", price_cents=1234)
        created_event = stream.receive_event_of_type(
            ["catalog.item.created"],
            timeout=5.0,
        )
        archived = catalog_items.set_status(int(created.json()["id"]), "archived")
        archived_event = stream.receive_event_of_type(
            ["catalog.item.updated"],
            timeout=5.0,
        )

    attach_json(
        "event evidence",
        {
            "created": [created.status_code, created_event.data],
            "archived": [archived.status_code, archived_event.data],
        },
    )

    assert created.status_code == 201
    assert archived.status_code == 200

    assert created_event.workspace == namespace.slug
    assert created_event.data["item"]["sku"] == sku
    assert created_event.data["cache_invalidated"] is True
    assert archived_event.workspace == namespace.slug
    assert archived_event.data["item"]["status"] == "archived"
    assert archived_event.sequence == created_event.sequence + 1


@allure.epic("Quality Engineering Lab")
@allure.feature("Event stream")
@allure.story("Async work")
@pytest.mark.api
def test_event_stream_reports_the_finished_background_job(
    sut_api_url: str,
    namespace: NamespaceLease,
    job_client: JobClient,
    owner_access_token: str,
) -> None:
    with connect_event_stream(sut_api_url, namespace.slug, owner_access_token) as stream:
        accepted = job_client.refresh_catalog_cache(
            namespace.slug,
            client_id=unique_client_id("stream"),
        )
        event = stream.receive_event_of_type(["job.succeeded"], timeout=10.0)

    attach_json("job event", event.data)

    assert event.workspace == namespace.slug
    assert event.data["job_id"] == accepted.job_id
    assert event.data["type"] == "catalog.cache_refresh"
    assert event.data["result"]["workspace_slug"] == namespace.slug


@allure.epic("Quality Engineering Lab")
@allure.feature("Event stream")
@allure.story("Handshake boundaries")
@pytest.mark.api
def test_event_stream_rejects_missing_authentication(
    sut_api_url: str,
    namespace: NamespaceLease,
) -> None:
    url = events_url(sut_api_url, namespace.slug)

    with pytest.raises(WebSocketHandshakeError) as caught:
        WebSocketConnection.connect(url, timeout=5.0)

    attach_json(
        "handshake evidence",
        {"status": caught.value.status_code, "payload": caught.value.payload},
    )

    assert caught.value.status_code == 401
    assert caught.value.payload["error"] == "authentication_required"


@allure.epic("Quality Engineering Lab")
@allure.feature("Event stream")
@allure.story("Handshake boundaries")
@pytest.mark.api
def test_event_stream_rejects_another_workspace(
    sut_api_url: str,
    settings: Settings,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
) -> None:
    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        tokens = peer_auth.tokens
        assert tokens is not None
        peer_token = tokens.access_token

    with pytest.raises(WebSocketHandshakeError) as caught:
        connect_event_stream(sut_api_url, namespace.slug, peer_token)

    assert caught.value.status_code == 403
    assert caught.value.payload["error"] == "permission_denied"


@allure.epic("Quality Engineering Lab")
@allure.feature("Event stream")
@allure.story("Handshake boundaries")
@pytest.mark.api
def test_event_stream_requires_the_websocket_upgrade(
    sut_api_url: str,
    namespace: NamespaceLease,
    owner_access_token: str,
) -> None:
    with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
        response = client.get(
            f"/api/v1/workspaces/{namespace.slug}/events",
            headers={"Authorization": f"Bearer {owner_access_token}"},
        )

    assert response.status_code == 426
    assert response.json()["error"] == "websocket_upgrade_required"


@allure.epic("Quality Engineering Lab")
@allure.feature("Event stream")
@allure.story("Backpressure")
@pytest.mark.api
def test_a_subscriber_that_stops_reading_cannot_block_writes(
    sut_api_url: str,
    namespace: NamespaceLease,
    catalog_items: CatalogApiFactory,
    owner_access_token: str,
) -> None:
    # The client connects and then never reads a frame.
    with connect_event_stream(sut_api_url, namespace.slug, owner_access_token):
        started = time.monotonic()
        responses = [
            catalog_items.create(
                name=f"Unread {index}",
                price_cents=index,
            )
            for index in range(3)
        ]
        elapsed = time.monotonic() - started

    attach_json(
        "backpressure evidence",
        {
            "statuses": [response.status_code for response in responses],
            "elapsed_seconds": elapsed,
        },
    )

    assert all(response.status_code == 201 for response in responses)
    assert elapsed < 5.0, "event fan-out must not run in the request thread"
