"""Query-plan evidence: when PostgreSQL uses the composite index, and when not."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import allure
import pytest
from qa_core.db import (
    DatabaseClient,
    actual_rows,
    execution_time_ms,
    explain_json,
    index_names,
    iter_plan_nodes,
    plan_node_types,
    plan_root,
    planning_time_ms,
    uses_index,
)

from tests.integration.conftest import BulkCatalog, ConnectionFactory

SCOPED_LOOKUP = (
    "SELECT id, sku FROM catalog_items "
    "WHERE workspace_id = %s AND status = 'active'"
)
UNINDEXED_PREDICATE = "SELECT count(*) FROM catalog_items WHERE price_cents > 10"
COMPOSITE_INDEX = "idx_catalog_items_workspace_status"


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Query plans")
@pytest.mark.integration
def test_composite_index_serves_the_workspace_scoped_lookup(
    database: DatabaseClient,
    bulk_catalog: BulkCatalog,
) -> None:
    plan = explain_json(
        database,
        SCOPED_LOOKUP,
        (bulk_catalog.focus_workspace_id,),
    )

    allure.attach(
        "\n".join(
            (
                f"node types: {plan_node_types(plan)}",
                f"indexes: {index_names(plan)}",
                f"actual rows: {actual_rows(plan)}",
                f"planning ms: {planning_time_ms(plan)}",
                f"execution ms: {execution_time_ms(plan)}",
            )
        ),
        name="Index plan evidence",
        attachment_type=allure.attachment_type.TEXT,
    )

    assert uses_index(plan)
    assert COMPOSITE_INDEX in index_names(plan)
    assert actual_rows(plan) == bulk_catalog.active_items_in_focus


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Query plans")
@pytest.mark.integration
def test_plan_reports_actual_rows_timing_and_buffer_counters(
    database: DatabaseClient,
    bulk_catalog: BulkCatalog,
) -> None:
    plan = explain_json(database, SCOPED_LOOKUP, (bulk_catalog.focus_workspace_id,))
    root = plan_root(plan)

    assert root["Actual Rows"] == bulk_catalog.active_items_in_focus
    assert float(root["Actual Total Time"]) >= 0.0
    assert "Shared Hit Blocks" in root
    assert "Shared Read Blocks" in root
    assert execution_time_ms(plan) >= 0.0
    assert planning_time_ms(plan) >= 0.0
    assert all("Node Type" in node for node in iter_plan_nodes(plan))


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Query plans")
@pytest.mark.integration
def test_disabling_index_scans_falls_back_to_a_sequential_scan(
    database: DatabaseClient,
    bulk_catalog: BulkCatalog,
    connection_factory: ConnectionFactory,
) -> None:
    sequential = connection_factory.open(
        autocommit=True, application_name="qa-week9-seqscan"
    )
    sequential.execute("SET enable_indexscan = off")
    sequential.execute("SET enable_bitmapscan = off")

    plan = explain_json(sequential, SCOPED_LOOKUP, (bulk_catalog.focus_workspace_id,))

    assert "Seq Scan" in plan_node_types(plan)
    assert index_names(plan) == ()
    assert actual_rows(plan) == bulk_catalog.active_items_in_focus


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Query plans")
@pytest.mark.integration
def test_predicate_without_an_index_scans_the_whole_table(
    database: DatabaseClient,
    bulk_catalog: BulkCatalog,
) -> None:
    plan = explain_json(database, UNINDEXED_PREDICATE)

    assert "Seq Scan" in plan_node_types(plan)
    assert index_names(plan) == ()


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Query plans")
@pytest.mark.integration
def test_workspace_scoped_lookup_does_not_scan_other_workspaces(
    database: DatabaseClient,
    bulk_catalog: BulkCatalog,
) -> None:
    total_rows = database.fetch_one("SELECT COUNT(*) AS rows FROM catalog_items")
    assert total_rows is not None
    scoped_plan = explain_json(
        database,
        SCOPED_LOOKUP,
        (bulk_catalog.focus_workspace_id,),
    )
    scan_nodes = [
        node
        for node in iter_plan_nodes(scoped_plan)
        if node.get("Node Type") == "Seq Scan"
    ]

    assert int(total_rows["rows"]) >= 20_000
    assert scan_nodes == []
    assert actual_rows(scoped_plan) < int(total_rows["rows"]) // 100
