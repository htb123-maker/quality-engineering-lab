"""Role and capability matrix mirrored from the local SUT.

The SUT owns the real decision, but tests need the expected answer *before*
they call an endpoint, otherwise an RBAC test can only assert "whatever the
server said". This mirror is therefore duplicated on purpose and kept honest by
``tests/unit/test_role_matrix.py``, which imports both copies and fails when
they drift apart.
"""

from __future__ import annotations

Roles = tuple[str, str, str, str]

ROLES: Roles = ("owner", "admin", "member", "viewer")

CAPABILITIES: tuple[str, ...] = (
    "audit:read",
    "catalog:read",
    "catalog:refresh",
    "catalog:write",
    "events:read",
    "jobs:read",
    "members:read",
    "members:write",
)

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "owner": frozenset(CAPABILITIES),
    "admin": frozenset(CAPABILITIES),
    "member": frozenset(
        {
            "catalog:read",
            "catalog:refresh",
            "catalog:write",
            "events:read",
            "jobs:read",
            "members:read",
        }
    ),
    "viewer": frozenset(
        {
            "catalog:read",
            "events:read",
            "jobs:read",
        }
    ),
}

# ``owner`` is never assignable through the members API: ownership transfer is
# not an API operation, and keeping it out of the contract removes the most
# obvious privilege-escalation door.
ASSIGNABLE_ROLES: tuple[str, ...] = ("admin", "member", "viewer")
ADMIN_ASSIGNABLE_ROLES: tuple[str, ...] = ("member", "viewer")

PRIVILEGE_ORDER: dict[str, int] = {
    "owner": 3,
    "admin": 2,
    "member": 1,
    "viewer": 0,
}


def capabilities_for(role: str) -> list[str]:
    """Return the sorted capabilities of one role."""

    return sorted(ROLE_CAPABILITIES.get(role, frozenset()))


def has_capability(role: str, capability: str) -> bool:
    """Return whether one role carries one capability."""

    return capability in ROLE_CAPABILITIES.get(role, frozenset())


def capability_matrix() -> dict[str, dict[str, bool]]:
    """Return a role-by-capability matrix that is easy to print as evidence."""

    return {
        role: {capability: has_capability(role, capability) for capability in CAPABILITIES}
        for role in ROLES
    }
