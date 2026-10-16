"""Read-only schema contract and constraint behaviour for the local database."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import allure
import psycopg
import pytest
from qa_core.data_factories import NamespaceFactory
from qa_core.db import (
    DatabaseClient,
    WorkspaceRepository,
    check_schema_contract,
    list_tables,
    list_views,
    table_contract,
    view_definition,
)


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Schema contract")
@pytest.mark.integration
def test_public_schema_matches_the_expected_contract(database: DatabaseClient) -> None:
    violations = check_schema_contract(database)

    assert violations == (), "\n".join(
        f"{violation.target}: {violation.message}" for violation in violations
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Schema contract")
@pytest.mark.integration
def test_seeded_tables_and_views_are_enumerated(database: DatabaseClient) -> None:
    assert list_tables(database) == ("catalog_items", "users", "workspaces")
    assert list_views(database) == ("workspace_catalog_summary",)


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Schema contract")
@pytest.mark.integration
def test_catalog_contract_reports_types_nullability_and_indexes(
    database: DatabaseClient,
) -> None:
    contract = table_contract(database, "catalog_items")

    assert contract.column_names == (
        "id",
        "workspace_id",
        "sku",
        "name",
        "price_cents",
        "status",
        "created_at",
    )
    price = contract.column("price_cents")
    assert price is not None
    assert price.data_type == "integer"
    assert price.is_nullable is False

    status = contract.constraint("catalog_items_status_check")
    assert status is not None
    assert status.kind == "check"
    assert "status = ANY" in status.definition

    index = contract.index("idx_catalog_items_workspace_status")
    assert index is not None
    assert index.definition.endswith("USING btree (workspace_id, status)")
    assert index.is_unique is False


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Schema contract")
@pytest.mark.integration
def test_summary_view_is_present_and_aggregates_active_items(
    database: DatabaseClient,
    namespace_factory: NamespaceFactory,
) -> None:
    identity = namespace_factory.create(tag="view", items=0)
    try:
        repository = WorkspaceRepository(database)
        for index, status in enumerate(("active", "active", "archived"), start=1):
            repository.upsert_item(
                workspace_id=identity.workspace_id,
                sku=f"VIEW-{index}",
                name=f"Viewed item {index}",
                price_cents=index * 1000,
                status=status,
            )

        row = database.fetch_one(
            """
            SELECT item_count, catalog_value_cents
            FROM workspace_catalog_summary
            WHERE workspace_id = %s
            """,
            (identity.workspace_id,),
        )
    finally:
        namespace_factory.purge(identity)

    assert row == {"item_count": 2, "catalog_value_cents": 3000}
    definition = view_definition(database, "workspace_catalog_summary")
    assert "status = 'active'" in definition


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Referential integrity")
@pytest.mark.integration
def test_deleting_a_workspace_cascades_to_users_and_items(
    database: DatabaseClient,
    namespace_factory: NamespaceFactory,
) -> None:
    identity = namespace_factory.create(tag="cascade", items=2)
    workspace_id = identity.workspace_id

    assert _child_counts(database, workspace_id) == (2, 2)
    deleted = namespace_factory.purge(identity)

    assert deleted == 1
    assert _child_counts(database, workspace_id) == (0, 0)
    remaining = database.fetch_one(
        "SELECT COUNT(*) AS workspaces FROM workspaces WHERE id = %s",
        (workspace_id,),
    )
    assert remaining == {"workspaces": 0}


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Constraints")
@pytest.mark.integration
def test_unique_sku_is_scoped_to_one_workspace(
    database: DatabaseClient,
    namespace_factory: NamespaceFactory,
) -> None:
    first = namespace_factory.create(tag="uniq-a")
    second = namespace_factory.create(tag="uniq-b")
    repository = WorkspaceRepository(database)
    try:
        repository.upsert_item(
            workspace_id=first.workspace_id,
            sku="SHARED-001",
            name="First",
            price_cents=100,
        )
        repository.upsert_item(
            workspace_id=second.workspace_id,
            sku="SHARED-001",
            name="Second",
            price_cents=100,
        )

        with pytest.raises(psycopg.errors.UniqueViolation) as error:
            database.execute(
                """
                INSERT INTO catalog_items (workspace_id, sku, name, price_cents)
                VALUES (%s, %s, %s, %s)
                """,
                (first.workspace_id, "SHARED-001", "Duplicate", 100),
            )

        rows = database.fetch_all(
            """
            SELECT workspace_id FROM catalog_items
            WHERE sku = %s ORDER BY workspace_id
            """,
            ("SHARED-001",),
        )
    finally:
        namespace_factory.purge(first)
        namespace_factory.purge(second)

    assert error.value.sqlstate == "23505"
    assert [row["workspace_id"] for row in rows] == [
        first.workspace_id,
        second.workspace_id,
    ]


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Constraints")
@pytest.mark.integration
def test_check_constraints_reject_invalid_role_and_negative_price(
    database: DatabaseClient,
    namespace_factory: NamespaceFactory,
) -> None:
    identity = namespace_factory.create(tag="checks")
    try:
        with pytest.raises(psycopg.errors.CheckViolation) as role_error:
            database.execute(
                """
                INSERT INTO users (workspace_id, email, display_name, role)
                VALUES (%s, %s, %s, %s)
                """,
                (identity.workspace_id, "auditor@example.test", "Auditor", "auditor"),
            )
        with pytest.raises(psycopg.errors.CheckViolation) as price_error:
            database.execute(
                """
                INSERT INTO catalog_items (workspace_id, sku, name, price_cents)
                VALUES (%s, %s, %s, %s)
                """,
                (identity.workspace_id, "NEG-001", "Negative", -1),
            )
        counts = database.fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM catalog_items WHERE workspace_id = %s) AS items
            """,
            (identity.workspace_id,),
        )
    finally:
        namespace_factory.purge(identity)

    assert role_error.value.sqlstate == "23514"
    assert price_error.value.sqlstate == "23514"
    assert counts == {"items": 0}


def _child_counts(database: DatabaseClient, workspace_id: int) -> tuple[int, int]:
    row = database.fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM users WHERE workspace_id = %s) AS users,
            (SELECT COUNT(*) FROM catalog_items WHERE workspace_id = %s) AS items
        """,
        (workspace_id, workspace_id),
    )
    if row is None:
        raise RuntimeError("child count query returned no row")
    return int(row["users"]), int(row["items"])
