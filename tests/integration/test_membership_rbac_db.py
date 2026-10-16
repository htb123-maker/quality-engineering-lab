"""Membership writes must land in PostgreSQL, and hostile input must not.

The RBAC tests assert status codes. These tests assert the *database*: a role
change is a row update, a removal is a row delete, an owner row survives a
refused demotion, and injection payloads leave the schema and the seed rows
exactly as they were.
"""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import allure
import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import NamespaceFactory, items_path
from qa_core.db import (
    DatabaseClient,
    SchemaViolation,
    check_schema_contract,
)
from qa_core.security import (
    HOSTILE_NAMES,
    MemberApiFactory,
    member_email,
)

from tests.integration.conftest import run_id


def _role(database: DatabaseClient, user_id: int) -> str:
    row = database.fetch_one("SELECT role FROM users WHERE id = %s", (user_id,))
    assert row is not None, f"user {user_id} disappeared"
    return str(row["role"])


def _user_count(database: DatabaseClient, workspace_id: int) -> int:
    row = database.fetch_one(
        "SELECT COUNT(*) AS total FROM users WHERE workspace_id = %s",
        (workspace_id,),
    )
    assert row is not None
    return int(row["total"])


@allure.epic("Quality Engineering Lab")
@allure.feature("Authorization")
@allure.story("Membership persistence")
@pytest.mark.integration
def test_role_changes_are_persisted_in_postgres(
    settings: Settings,
    database: DatabaseClient,
    namespace_factory: NamespaceFactory,
) -> None:
    identity = namespace_factory.create(tag=f"week11-role-{run_id()[:4]}")
    try:
        with AuthClient.from_settings(settings) as auth:
            auth.login(identity.owner_email, settings.auth_test_password)
            members = MemberApiFactory(auth, identity.slug)
            member = members.invite("viewer")

            assert _role(database, member.user_id) == "viewer"
            promoted = members.change_role(member.user_id, "member")
            stored = _role(database, member.user_id)

            with AuthClient.from_settings(settings) as promoted_auth:
                promoted_auth.login(member.email, settings.auth_test_password)
                permissions = promoted_auth.get("/api/v1/auth/permissions")

        allure.attach(
            "\n".join(
                [
                    f"PATCH status: {promoted.status_code}",
                    f"stored role: {stored}",
                    f"capabilities: {permissions.json()['capabilities']}",
                ]
            ),
            name="role change evidence",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert promoted.status_code == 200
        assert stored == "member"
        assert permissions.status_code == 200
        assert "catalog:write" in permissions.json()["capabilities"]
        assert "members:write" not in permissions.json()["capabilities"]
    finally:
        namespace_factory.purge(identity)


@allure.feature("Authorization")
@allure.story("Membership persistence")
@pytest.mark.integration
def test_removing_a_member_deletes_the_row(
    settings: Settings,
    database: DatabaseClient,
    namespace_factory: NamespaceFactory,
) -> None:
    identity = namespace_factory.create(tag=f"week11-remove-{run_id()[:4]}")
    try:
        before = _user_count(database, identity.workspace_id)
        with AuthClient.from_settings(settings) as auth:
            auth.login(identity.owner_email, settings.auth_test_password)
            members = MemberApiFactory(auth, identity.slug)
            member = members.invite("viewer")
            with_member = _user_count(database, identity.workspace_id)

            removed = members.remove(member.user_id)
            after = _user_count(database, identity.workspace_id)

        assert with_member == before + 1
        assert removed.status_code == 204
        assert after == before
        allure.attach(
            f"users: {before} -> {with_member} -> {after}",
            name="member removal evidence",
            attachment_type=allure.attachment_type.TEXT,
        )
    finally:
        namespace_factory.purge(identity)


@allure.feature("Authorization")
@allure.story("Owner protection")
@pytest.mark.integration
def test_a_refused_demotion_leaves_the_owner_row_untouched(
    settings: Settings,
    database: DatabaseClient,
    namespace_factory: NamespaceFactory,
) -> None:
    identity = namespace_factory.create(tag=f"week11-owner-{run_id()[:4]}")
    try:
        with AuthClient.from_settings(settings) as auth:
            auth.login(identity.owner_email, settings.auth_test_password)
            members = MemberApiFactory(auth, identity.slug)
            refused = members.change_role(identity.owner.user_id, "viewer")

        assert refused.status_code == 403
        assert refused.json()["error"] == "owner_protected"
        assert _role(database, identity.owner.user_id) == "owner"
        owners = database.fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM users
            WHERE workspace_id = %s AND role = 'owner'
            """,
            (identity.workspace_id,),
        )
        assert owners is not None
        assert int(owners["total"]) == 1
    finally:
        namespace_factory.purge(identity)


@allure.feature("Input security")
@allure.story("Injection containment")
@pytest.mark.integration
def test_injection_payloads_leave_the_schema_and_seed_rows_intact(
    settings: Settings,
    database: DatabaseClient,
    namespace_factory: NamespaceFactory,
) -> None:
    """The payloads may be stored, but they must never change the database."""

    identity = namespace_factory.create(tag=f"week11-inject-{run_id()[:4]}")
    try:
        before_contract: tuple[SchemaViolation, ...] = check_schema_contract(database)
        before_seed = namespace_factory.seed_counts()

        statuses: dict[str, int] = {}
        with AuthClient.from_settings(settings) as auth:
            auth.login(identity.owner_email, settings.auth_test_password)
            for label, name in HOSTILE_NAMES.items():
                sku_tag = label.upper().replace("_", "-")[:8]
                response = auth.post(
                    items_path(identity.slug),
                    json={
                        "sku": f"QA11-{sku_tag}-0001",
                        "name": name,
                        "price_cents": 100,
                    },
                    headers={"X-QA-Client-Id": f"qa11-inject-{label}"},
                )
                statuses[label] = response.status_code
            members = MemberApiFactory(auth, identity.slug)
            injected_email = members.auth.post(
                f"/api/v1/workspaces/{identity.slug}/members",
                json={
                    "email": member_email(identity.slug, "sql"),
                    "display_name": HOSTILE_NAMES["sql_injection"],
                    "role": "viewer",
                },
                headers={"X-QA-Client-Id": "qa11-inject-member"},
            )

        after_contract = check_schema_contract(database)
        after_seed = namespace_factory.seed_counts()
        tables = database.fetch_all(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
        stored_names = database.fetch_all(
            "SELECT name FROM catalog_items WHERE workspace_id = %s ORDER BY id",
            (identity.workspace_id,),
        )

        allure.attach(
            "\n".join(
                [
                    f"write statuses: {statuses}",
                    f"member invite: {injected_email.status_code}",
                    f"schema violations before/after: "
                    f"{len(before_contract)} / {len(after_contract)}",
                    f"tables: {[row['table_name'] for row in tables]}",
                ]
            ),
            name="injection containment evidence",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert set(statuses.values()) == {201}
        assert injected_email.status_code == 201
        assert before_contract == ()
        assert after_contract == ()
        assert before_seed == after_seed
        assert sorted(row["table_name"] for row in tables) == [
            "catalog_items",
            "users",
            "workspaces",
        ]
        assert [row["name"] for row in stored_names] == list(HOSTILE_NAMES.values())
    finally:
        namespace_factory.purge(identity)
