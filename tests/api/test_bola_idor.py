"""BOLA/IDOR: object identifiers must not work across tenants.

Week 8 proved that parallel workers cannot see each other's *data*. Week 11
proves the harder half: knowing a valid identifier does not let a caller reach
another tenant's object, and the refusal does not become an existence oracle.
"""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from uuid import uuid4

import allure
import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory, item_path, items_path
from qa_core.events import WebSocketHandshakeError
from qa_core.jobs import JobClient, job_path
from qa_core.resource_pools import NamespaceLease
from qa_core.security import MemberApiFactory, members_path

from tests.api.conftest import (
    attach_json,
    connect_event_stream,
    owner_session,
    unique_client_id,
)


@allure.epic("Quality Engineering Lab")
@allure.feature("Authorization")
@allure.story("BOLA")
@pytest.mark.api
def test_foreign_catalog_item_id_is_hidden_behind_a_not_found(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    """A real id from another tenant and a made-up id must look identical."""

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        peer_items = CatalogApiFactory(
            auth=peer_auth,
            workspace_slug=peer_namespace.slug,
            client_id=unique_client_id("peer-factory"),
        )
        created = peer_items.create(name="Peer secret")
        assert created.status_code == 201
        foreign_id = int(created.json()["id"])
        foreign_payload = created.json()
        peer_items.cleanup()

    foreign = owner_auth.get(item_path(foreign_id, namespace.slug))
    unknown = owner_auth.get(item_path(99_999_999, namespace.slug))

    assert foreign.status_code == 404
    assert unknown.status_code == 404
    assert foreign.json()["error"] == "item_not_found"
    assert unknown.json()["error"] == "item_not_found"
    attached = f"{foreign.text}{unknown.text}"
    assert str(foreign_payload["sku"]) not in attached
    assert str(foreign_payload["name"]) not in attached
    attach_json(
        "Foreign item id",
        {
            "foreign_id": foreign_id,
            "foreign_response": foreign.json(),
            "unknown_response": unknown.json(),
        },
    )


@allure.feature("Authorization")
@allure.story("BOLA")
@pytest.mark.api
def test_member_ids_are_scoped_to_their_own_workspace(
    owner_auth: AuthClient,
    member_api: MemberApiFactory,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    """Knowing another tenant's user id must not address that user."""

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        peer_me = peer_auth.get("/api/v1/auth/me").json()
    peer_user_id = int(peer_me["id"])

    changed = member_api.change_role(peer_user_id, "viewer")
    removed = member_api.remove(peer_user_id)
    listed = owner_auth.get(members_path(namespace.slug))

    assert changed.status_code == 404
    assert changed.json()["error"] == "member_not_found"
    assert removed.status_code == 404
    assert removed.json()["error"] == "member_not_found"
    member_ids = {int(member["id"]) for member in listed.json()["members"]}
    assert peer_user_id not in member_ids
    attach_json(
        "Foreign member id",
        {
            "peer_user_id": peer_user_id,
            "patch": changed.json(),
            "delete": removed.json(),
            "own_members": sorted(member_ids),
        },
    )


@allure.feature("Authorization")
@allure.story("BOLA")
@pytest.mark.api
def test_member_list_of_a_foreign_workspace_leaks_no_rows(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
) -> None:
    response = owner_auth.get(members_path(peer_namespace.slug))

    assert response.status_code == 403
    assert response.json()["error"] == "permission_denied"
    assert peer_namespace.owner_email not in response.text
    assert peer_namespace.slug not in response.text
    attach_json("Foreign members list", response.json())


@allure.feature("Authorization")
@allure.story("BOLA")
@pytest.mark.api
def test_tenant_check_runs_before_the_object_lookup(
    owner_auth: AuthClient,
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    """A foreign caller with a *valid* local id still gets 403, not 200."""

    created = catalog_items.create(name="Local item")
    local_id = int(created.json()["id"])

    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        response = peer_auth.get(item_path(local_id, namespace.slug))

    assert response.status_code == 403
    assert response.json()["error"] == "permission_denied"
    attach_json(
        "Cross-tenant read",
        {"local_item_id": local_id, "status": response.status_code},
    )


@allure.feature("Authorization")
@allure.story("BOLA")
@pytest.mark.api
def test_job_read_never_returns_another_tenants_job(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
    settings: Settings,
) -> None:
    with owner_session(peer_namespace.owner_email, settings) as peer_auth:
        peer_jobs = JobClient.from_auth(peer_auth)
        accepted = peer_jobs.refresh_catalog_cache(peer_namespace.slug)
        foreign = owner_auth.get(job_path(accepted.job_id))
        unknown = owner_auth.get(job_path(uuid4().hex))

    assert foreign.status_code == 403
    assert foreign.json()["error"] == "permission_denied"
    assert peer_namespace.slug not in foreign.text
    assert accepted.job_id not in foreign.text
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "job_not_found"
    attach_json(
        "Foreign job read",
        {
            "foreign": foreign.json(),
            "unknown": unknown.json(),
        },
    )


@allure.feature("Authorization")
@allure.story("BOLA")
@pytest.mark.api
def test_event_stream_refuses_a_foreign_workspace(
    sut_api_url: str,
    owner_access_token: str,
    namespace: NamespaceLease,
    peer_namespace: NamespaceLease,
) -> None:
    del namespace

    with pytest.raises(WebSocketHandshakeError) as caught:
        connect_event_stream(
            sut_api_url,
            peer_namespace.slug,
            owner_access_token,
        )

    assert caught.value.status_code == 403
    assert caught.value.payload["error"] == "permission_denied"
    attach_json("Foreign event stream", caught.value.payload)


@allure.feature("Authorization")
@allure.story("BOLA")
@pytest.mark.api
def test_write_paths_refuse_another_tenants_workspace(
    owner_auth: AuthClient,
    peer_namespace: NamespaceLease,
) -> None:
    """Documented tradeoff: cross-tenant writes stay 403, not 404."""

    created = owner_auth.post(
        items_path(peer_namespace.slug),
        json={"sku": "QA11-BOLA-0001", "name": "nope", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id("bola-write")},
    )
    refreshed = owner_auth.post(
        f"/api/v1/workspaces/{peer_namespace.slug}/catalog/cache/refresh",
        json={},
        headers={"X-QA-Client-Id": unique_client_id("bola-refresh")},
    )

    assert created.status_code == 403
    assert refreshed.status_code == 403
    assert created.json()["error"] == "permission_denied"
    assert refreshed.json()["error"] == "permission_denied"
    attach_json(
        "Cross-tenant writes",
        {"create": created.json(), "refresh": refreshed.json()},
    )


@allure.feature("Authorization")
@allure.story("BOLA")
@pytest.mark.api
def test_unknown_object_shapes_do_not_reveal_the_tenants_catalog(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    """Sequential id probing returns only the local namespace's own rows."""

    seen: list[tuple[int, int]] = []
    for candidate in range(1, 9):
        response = owner_auth.get(item_path(candidate, namespace.slug))
        seen.append((candidate, response.status_code))
        assert response.status_code in {200, 404}

    attached = owner_auth.get(f"/api/v1/workspaces/{namespace.slug}/catalog")
    owned = {int(item["id"]) for item in attached.json()["items"]}
    for candidate, status in seen:
        if candidate in owned:
            assert status == 200
        else:
            assert status == 404
    attach_json("Id probe", {"probe": seen, "owned": sorted(owned)})
