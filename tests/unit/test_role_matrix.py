"""The test-side role matrix must stay identical to the SUT's registry."""

from __future__ import annotations

import app as sut_app
from qa_core.security import (
    ADMIN_ASSIGNABLE_ROLES,
    ASSIGNABLE_ROLES,
    CAPABILITIES,
    PRIVILEGE_ORDER,
    ROLE_CAPABILITIES,
    ROLES,
    capabilities_for,
    capability_matrix,
    has_capability,
)


def test_the_mirror_matches_the_sut_registry() -> None:
    """A drifted mirror would make every RBAC assertion meaningless."""

    assert set(ROLE_CAPABILITIES) == set(sut_app.ROLE_CAPABILITIES)
    for role, capabilities in ROLE_CAPABILITIES.items():
        assert capabilities == sut_app.ROLE_CAPABILITIES[role], role


def test_the_sut_capability_helper_agrees_with_the_mirror() -> None:
    for role in ROLES:
        assert sut_app.capabilities_for(role) == capabilities_for(role)
        for capability in CAPABILITIES:
            assert sut_app.has_capability(role, capability) == has_capability(
                role,
                capability,
            )


def test_roles_are_ordered_by_privilege() -> None:
    order = [PRIVILEGE_ORDER[role] for role in ROLES]
    assert order == sorted(order, reverse=True)
    assert set(PRIVILEGE_ORDER) == set(ROLES)


def test_owner_is_never_assignable_through_the_api() -> None:
    """Ownership transfer is not an API operation, in either copy."""

    assert "owner" not in ASSIGNABLE_ROLES
    assert "owner" not in ADMIN_ASSIGNABLE_ROLES
    assert set(ASSIGNABLE_ROLES) == set(sut_app.ASSIGNABLE_ROLES)
    assert set(ADMIN_ASSIGNABLE_ROLES) == set(sut_app.ADMIN_ASSIGNABLE_ROLES)


def test_the_matrix_covers_every_role_and_capability() -> None:
    matrix = capability_matrix()

    assert set(matrix) == set(ROLES)
    for role, row in matrix.items():
        assert set(row) == set(CAPABILITIES), role
        assert row["catalog:read"], role


def test_only_owners_and_admins_can_write_membership() -> None:
    writers = {
        role for role in ROLES if has_capability(role, "members:write")
    }
    readers = {role for role in ROLES if has_capability(role, "members:read")}
    writers_catalog = {
        role for role in ROLES if has_capability(role, "catalog:write")
    }

    assert writers == {"owner", "admin"}
    assert readers == {"owner", "admin", "member"}
    assert writers_catalog == {"owner", "admin", "member"}
