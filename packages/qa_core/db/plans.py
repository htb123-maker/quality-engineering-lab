"""Helpers for reading PostgreSQL query plans as structured data.

``EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`` returns what actually happened, not
what the planner guessed: node types, estimated rows, actual rows, timing, and
buffer counts. Tests can then assert "the composite index was used" without
depending on the human-readable text format.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from qa_core.db.client import DatabaseClient, Params

PlanNode = dict[str, Any]
Plan = dict[str, Any]


def explain_json(
    db: DatabaseClient,
    sql: str,
    params: Params | None = None,
    *,
    analyze: bool = True,
    buffers: bool = True,
    verbose: bool = False,
) -> Plan:
    """Run ``EXPLAIN`` on one statement and return the first plan as a mapping."""

    options = ["FORMAT JSON"]
    if analyze:
        options.append("ANALYZE")
    if buffers:
        options.append("BUFFERS")
    if verbose:
        options.append("VERBOSE")

    row = db.fetch_one(f"EXPLAIN ({', '.join(options)}) {sql}", params)
    if row is None:
        raise RuntimeError("EXPLAIN returned no row")
    payload: Any = row["QUERY PLAN"]
    if isinstance(payload, list):
        if not payload:
            raise RuntimeError("EXPLAIN returned an empty plan list")
        payload = payload[0]
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected EXPLAIN payload type {type(payload).__name__}")
    return payload


def plan_root(plan: Plan) -> PlanNode:
    """Return the root node of an ``EXPLAIN (FORMAT JSON)`` document."""

    root = plan.get("Plan")
    if not isinstance(root, dict):
        raise RuntimeError("EXPLAIN payload has no 'Plan' object")
    return root


def iter_plan_nodes(plan: Plan) -> Iterator[PlanNode]:
    """Yield every node in the plan tree, parents before children."""

    def walk(node: PlanNode) -> Iterator[PlanNode]:
        yield node
        children = node.get("Plans")
        if isinstance(children, Sequence):
            for child in children:
                if isinstance(child, dict):
                    yield from walk(child)

    yield from walk(plan_root(plan))


def plan_node_types(plan: Plan) -> tuple[str, ...]:
    """Return the node types in the plan tree, parents before children."""

    return tuple(str(node.get("Node Type", "unknown")) for node in iter_plan_nodes(plan))


def find_nodes(plan: Plan, node_type: str) -> tuple[PlanNode, ...]:
    """Return every node whose ``Node Type`` matches exactly."""

    return tuple(
        node for node in iter_plan_nodes(plan) if node.get("Node Type") == node_type
    )


def index_names(plan: Plan) -> tuple[str, ...]:
    """Return the indexes named anywhere in the plan tree."""

    return tuple(
        str(node["Index Name"])
        for node in iter_plan_nodes(plan)
        if node.get("Index Name") is not None
    )


def uses_index(plan: Plan) -> bool:
    """Return whether the plan reads through an index or bitmap index."""

    return bool(index_names(plan))


def node_metric(node: Mapping[str, Any], name: str) -> Any:
    """Return one metric from a plan node, raising a clear error if absent."""

    if name not in node:
        raise KeyError(f"plan node {node.get('Node Type')!r} has no metric {name!r}")
    return node[name]


def actual_rows(plan: Plan) -> int:
    """Return the rows the root node actually produced."""

    return int(node_metric(plan_root(plan), "Actual Rows"))


def planning_time_ms(plan: Plan) -> float:
    """Return the planning time in milliseconds."""

    return float(plan.get("Planning Time", 0.0))


def execution_time_ms(plan: Plan) -> float:
    """Return the execution time in milliseconds."""

    return float(plan.get("Execution Time", 0.0))
