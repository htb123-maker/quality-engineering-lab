"""Role-based access control driven by one explicit capability matrix.

Every case reads its expected answer from ``qa_core.security.roles`` instead of
hard-coding a status per test, so the suite proves the *matrix* rather than
individual lucky responses. ``tests/unit/test_role_matrix.py`` pins the mirror
to the SUT's own registry.
"""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import allure
import httpx
import pytest
from qa_core.auth import AuthClient, RefreshTokenInvalid
from qa_core.contracts import PermissionsResponse
from qa_core.data_factories import CatalogApiFactory, item_path, items_path
from qa_core.resource_pools import NamespaceLease
from qa_core.security import (
    ROLES,
    MemberApiFactory,
    capabilities_for,
    capability_matrix,
    has_capability,
    member_path,
    members_path,
)

from tests.api.conftest import attach_json, unique_client_id

PERMISSIONS_PATH = "/api/v1/auth/permissions"
AUDIT_PATH = "/api/v1/admin/audit"


def _expect(response: httpx.Response, capability: str, role: str) -> None:
    """Assert that the response agrees with the capability matrix."""

    if has_capability(role, capability):
        assert response.status_code < 400, (
            f"{role} should hold {capability}: {response.status_code} "
            f"{response.text}"
        )
    else:
        assert response.status_code == 403, (
            f"{role} should be denied {capability}: {response.status_code} "
            f"{response.text}"
        )
        assert response.json()["error"] == "permission_denied"


@allure.epic("Quality Engineering Lab")
@allure.feature("Authorization")
@allure.story("Role matrix")
@pytest.mark.api
@pytest.mark.parametrize("role", ROLES)
def test_permissions_endpoint_describes_the_role_matrix(
    role: str,
    role_sessions: dict[str, AuthClient],
    namespace: NamespaceLease,
) -> None:
    """The SUT must answer with exactly the capabilities the mirror predicts."""

    response = role_sessions[role].get(PERMISSIONS_PATH)

    assert response.status_code == 200
    payload = PermissionsResponse.model_validate(response.json())
    assert payload.role == role
    assert payload.workspace_slug == namespace.slug
    assert payload.capabilities == capabilities_for(role)
    attach_json(
        f"{role} capabilities",
        {
            "role": role,
            "capabilities": payload.capabilities,
            "matrix": capability_matrix()[role],
        },
    )


@allure.feature("Authorization")
@allure.story("Role matrix")
@pytest.mark.api
@pytest.mark.parametrize("role", ROLES)
def test_catalog_write_follows_the_capability_matrix(
    role: str,
    role_sessions: dict[str, AuthClient],
    namespace: NamespaceLease,
) -> None:
    response = role_sessions[role].post(
        items_path(namespace.slug),
        json={"sku": "QA11-RBAC-0001", "name": "matrix", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id(f"rbac-{role}")},
    )

    _expect(response, "catalog:write", role)
    attach_json(
        f"{role} catalog write",
        {"status": response.status_code, "body": response.json()},
    )


@allure.feature("Authorization")
@allure.story("Role matrix")
@pytest.mark.api
@pytest.mark.parametrize("role", ROLES)
def test_catalog_item_read_follows_the_capability_matrix(
    role: str,
    role_sessions: dict[str, AuthClient],
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
) -> None:
    created = catalog_items.create(name="matrix item")
    assert created.status_code == 201
    item_id = int(created.json()["id"])

    response = role_sessions[role].get(item_path(item_id, namespace.slug))

    _expect(response, "catalog:read", role)


@allure.feature("Authorization")
@allure.story("Role matrix")
@pytest.mark.api
@pytest.mark.parametrize("role", ROLES)
def test_audit_read_follows_the_capability_matrix(
    role: str,
    role_sessions: dict[str, AuthClient],
) -> None:
    response = role_sessions[role].get(AUDIT_PATH)

    _expect(response, "audit:read", role)
    attach_json(f"{role} audit", {"status": response.status_code})


@allure.feature("Authorization")
@allure.story("Role matrix")
@pytest.mark.api
@pytest.mark.parametrize("role", ROLES)
def test_members_read_follows_the_capability_matrix(
    role: str,
    role_sessions: dict[str, AuthClient],
    namespace: NamespaceLease,
) -> None:
    response = role_sessions[role].get(members_path(namespace.slug))

    _expect(response, "members:read", role)


@allure.feature("Authorization")
@allure.story("Role matrix")
@pytest.mark.api
@pytest.mark.parametrize("role", ROLES)
def test_member_invite_follows_the_capability_matrix(
    role: str,
    role_sessions: dict[str, AuthClient],
    namespace: NamespaceLease,
) -> None:
    response = role_sessions[role].post(
        members_path(namespace.slug),
        json={
            "email": f"invitee-{role}@example.com",
            "display_name": f"{role} invitee",
            "role": "viewer",
        },
        headers={"X-QA-Client-Id": unique_client_id(f"invite-{role}")},
    )

    _expect(response, "members:write", role)
    attach_json(
        f"{role} invite",
        {"status": response.status_code, "body": response.json()},
    )


@allure.feature("Authorization")
@allure.story("Role matrix")
@pytest.mark.api
@pytest.mark.parametrize("role", ROLES)
def test_cache_refresh_follows_the_capability_matrix(
    role: str,
    role_sessions: dict[str, AuthClient],
    namespace: NamespaceLease,
) -> None:
    response = role_sessions[role].post(
        f"/api/v1/workspaces/{namespace.slug}/catalog/cache/refresh",
        json={},
        headers={"X-QA-Client-Id": unique_client_id(f"refresh-{role}")},
    )

    _expect(response, "catalog:refresh", role)


@allure.feature("Authorization")
@allure.story("Privilege escalation")
@pytest.mark.api
def test_admin_cannot_grant_the_admin_role(
    role_sessions: dict[str, AuthClient],
    namespace: NamespaceLease,
) -> None:
    """Only an owner may create another admin; admin is not self-replicating."""

    response = role_sessions["admin"].post(
        members_path(namespace.slug),
        json={
            "email": "peer-admin@example.com",
            "display_name": "Peer admin",
            "role": "admin",
        },
        headers={"X-QA-Client-Id": unique_client_id("escalate")},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "role_escalation_forbidden"
    attach_json("Escalation attempt", response.json())


@allure.feature("Authorization")
@allure.story("Privilege escalation")
@pytest.mark.api
def test_owner_role_is_not_assignable_through_the_api(
    role_sessions: dict[str, AuthClient],
    namespace: NamespaceLease,
) -> None:
    response = role_sessions["owner"].post(
        members_path(namespace.slug),
        json={
            "email": "second-owner@example.com",
            "display_name": "Second owner",
            "role": "owner",
        },
        headers={"X-QA-Client-Id": unique_client_id("owner-role")},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_failed"
    assert [field["field"] for field in body["fields"]] == ["$.role"]


@allure.feature("Authorization")
@allure.story("Owner protection")
@pytest.mark.api
def test_owner_membership_cannot_be_demoted_or_removed(
    role_sessions: dict[str, AuthClient],
    member_api: MemberApiFactory,
    namespace: NamespaceLease,
) -> None:
    owner = role_sessions["owner"]
    me = owner.get("/api/v1/auth/me").json()
    owner_id = int(me["id"])

    demote = member_api.change_role(owner_id, "viewer")
    remove = member_api.remove(owner_id)

    assert demote.status_code == 403
    assert demote.json()["error"] == "owner_protected"
    assert remove.status_code == 403
    assert remove.json()["error"] == "owner_protected"
    attach_json(
        "Owner protection",
        {"demote": demote.json(), "remove": remove.json()},
    )


@allure.feature("Authorization")
@allure.story("Owner protection")
@pytest.mark.api
def test_member_cannot_change_or_remove_its_own_membership(
    role_sessions: dict[str, AuthClient],
    namespace: NamespaceLease,
) -> None:
    """An admin holds members:write, but still may not edit itself."""

    admin = role_sessions["admin"]
    me = admin.get("/api/v1/auth/me").json()
    admin_id = int(me["id"])

    changed = admin.request(
        "PATCH",
        member_path(namespace.slug, admin_id),
        json={"role": "member"},
        headers={"X-QA-Client-Id": unique_client_id("self-role")},
    )
    deleted = admin.request(
        "DELETE",
        member_path(namespace.slug, admin_id),
        headers={"X-QA-Client-Id": unique_client_id("self-delete")},
    )

    assert changed.status_code == 403
    assert changed.json()["error"] == "self_modification_forbidden"
    assert deleted.status_code == 403
    assert deleted.json()["error"] == "self_modification_forbidden"
    attach_json(
        "Self modification",
        {"patch": changed.json(), "delete": deleted.json()},
    )


@allure.feature("Authorization")
@allure.story("Membership lifecycle")
@pytest.mark.api
def test_a_removed_member_loses_access_immediately(
    role_sessions: dict[str, AuthClient],
    member_api: MemberApiFactory,
    namespace: NamespaceLease,
) -> None:
    """Removal is a database delete, so the next request fails authentication."""

    removed = role_sessions["viewer"]
    me = removed.get("/api/v1/auth/me").json()

    before = removed.get(members_path(namespace.slug))
    response = member_api.remove(int(me["id"]))
    after = removed.get(members_path(namespace.slug), refresh_on_401=False)
    with pytest.raises(RefreshTokenInvalid):
        removed.refresh()

    assert before.status_code in {200, 403}
    assert response.status_code == 204
    assert after.status_code == 401
    assert after.json()["error"] == "invalid_token"
    attach_json(
        "Removed member",
        {
            "user_id": me["id"],
            "remove": response.status_code,
            "after": after.json(),
        },
    )
