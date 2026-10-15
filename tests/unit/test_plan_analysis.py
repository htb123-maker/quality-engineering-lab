"""Unit tests for reading PostgreSQL query plans as structured data."""

from __future__ import annotations

import pytest
from qa_core.db import (
    actual_rows,
    execution_time_ms,
    find_nodes,
    index_names,
    iter_plan_nodes,
    node_metric,
    plan_node_types,
    plan_root,
    planning_time_ms,
    uses_index,
)


def _plan_with_index() -> dict[str, object]:
    return {
        "Plan": {
            "Node Type": "Bitmap Heap Scan",
            "Actual Rows": 90,
            "Actual Total Time": 0.42,
            "Shared Hit Blocks": 12,
            "Plans": [
                {
                    "Node Type": "Bitmap Index Scan",
                    "Index Name": "idx_catalog_items_workspace_status",
                    "Actual Rows": 0,
                    "Actual Total Time": 0.05,
                    "Shared Hit Blocks": 3,
                }
            ],
        },
        "Planning Time": 0.31,
        "Execution Time": 0.77,
        "Triggers": [],
    }


def _plan_with_sequential_scan() -> dict[str, object]:
    return {
        "Plan": {
            "Node Type": "Aggregate",
            "Actual Rows": 1,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Actual Rows": 20_000,
                    "Filter": "(price_cents > 10)",
                }
            ],
        },
        "Planning Time": 0.2,
        "Execution Time": 3.5,
    }


@pytest.mark.unit
def test_plan_nodes_are_walked_parents_before_children() -> None:
    plan = _plan_with_index()

    assert plan_node_types(plan) == ("Bitmap Heap Scan", "Bitmap Index Scan")
    assert plan_root(plan)["Node Type"] == "Bitmap Heap Scan"
    assert len(list(iter_plan_nodes(plan))) == 2


@pytest.mark.unit
def test_index_names_reports_every_index_in_the_tree() -> None:
    assert index_names(_plan_with_index()) == (
        "idx_catalog_items_workspace_status",
    )
    assert uses_index(_plan_with_index()) is True
    assert index_names(_plan_with_sequential_scan()) == ()
    assert uses_index(_plan_with_sequential_scan()) is False


@pytest.mark.unit
def test_find_nodes_and_metrics_read_the_reported_values() -> None:
    plan = _plan_with_index()
    index_nodes = find_nodes(plan, "Bitmap Index Scan")

    assert len(index_nodes) == 1
    assert node_metric(index_nodes[0], "Index Name") == (
        "idx_catalog_items_workspace_status"
    )
    assert actual_rows(plan) == 90
    assert planning_time_ms(plan) == pytest.approx(0.31)
    assert execution_time_ms(plan) == pytest.approx(0.77)


@pytest.mark.unit
def test_missing_metrics_and_plans_raise_clear_errors() -> None:
    with pytest.raises(KeyError, match="Actual Rows"):
        node_metric({"Node Type": "Result"}, "Actual Rows")
    with pytest.raises(RuntimeError, match="no 'Plan' object"):
        plan_root({"Execution Time": 1.0})
    with pytest.raises(KeyError, match="has no metric 'Actual Rows'"):
        actual_rows({"Plan": {"Node Type": "Result"}})
