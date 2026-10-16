"""Invite and manage workspace members through the SUT API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

import httpx

from qa_core.auth import AuthClient


def members_path(workspace_slug: str) -> str:
    """Return the members collection path for one workspace."""

    return f"/api/v1/workspaces/{workspace_slug}/members"


def member_path(workspace_slug: str, user_id: int) -> str:
    """Return the member path for one workspace user."""

    return f"{members_path(workspace_slug)}/{user_id}"


def member_email(workspace_slug: str, tag: str = "member") -> str:
    """Return a unique, contract-valid email inside one workspace."""

    return f"{tag}-{uuid4().hex[:10]}@{workspace_slug}.example"


@dataclass(frozen=True)
class MemberIdentity:
    """One member created through the API."""

    user_id: int
    email: str
    role: str


class MemberApiFactory:
    """Create members for one workspace so RBAC tests can log in as them."""

    def __init__(
        self,
        auth: AuthClient,
        workspace_slug: str,
        *,
        client_id: Callable[[str], str] | None = None,
    ) -> None:
        self.auth = auth
        self.workspace_slug = workspace_slug
        self._client_id = client_id or (lambda tag: f"qa11-{tag}-{uuid4().hex[:10]}")
        self.created: list[MemberIdentity] = []

    def invite(
        self,
        role: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> MemberIdentity:
        """Invite one member and fail loudly when the invite is refused."""

        resolved_email = email or member_email(self.workspace_slug, role)
        response = self.auth.post(
            members_path(self.workspace_slug),
            json={
                "email": resolved_email,
                "display_name": display_name or f"QA {role.title()}",
                "role": role,
            },
            headers={"X-QA-Client-Id": self._client_id("members")},
        )
        if response.status_code != 201:
            raise AssertionError(
                f"inviting a {role} returned {response.status_code}: {response.text}"
            )
        payload = response.json()
        identity = MemberIdentity(
            user_id=int(payload["id"]),
            email=str(payload["email"]),
            role=str(payload["role"]),
        )
        self.created.append(identity)
        return identity

    def list_members(self) -> httpx.Response:
        """Return the members list response for this workspace."""

        return self.auth.get(members_path(self.workspace_slug))

    def change_role(self, user_id: int, role: str) -> httpx.Response:
        """Request one member role change."""

        return self.auth.request(
            "PATCH",
            member_path(self.workspace_slug, user_id),
            json={"role": role},
            headers={"X-QA-Client-Id": self._client_id("member-role")},
        )

    def remove(self, user_id: int) -> httpx.Response:
        """Request the removal of one member."""

        return self.auth.request(
            "DELETE",
            member_path(self.workspace_slug, user_id),
            headers={"X-QA-Client-Id": self._client_id("member-remove")},
        )
