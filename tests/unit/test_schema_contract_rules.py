"""Unit tests for the schema-contract comparison rules."""

from __future__ import annotations

from dataclasses import replace

import pytest
from qa_core.db import (
    EXPECTED_TABLES,
    EXPECTED_VIEWS,
    ColumnContract,
    ConstraintContract,
    IndexContract,
    SchemaViolation,
    TableContract,
    TableExpectation,
    validate_schema,
)


def _contract_from(expectation: TableExpectation) -> TableContract:
    """Build a contract that satisfies one expectation exactly."""

    constraints = [
        ConstraintContract(name=name, kind="misc", definition="")
        for name in expectation.constraint_names
    ]
    constraints.extend(
        ConstraintContract(
            name=f"fragment_{index}",
            kind="check",
            definition=fragment,
        )
        for index, fragment in enumerate(expectation.constraint_fragments)
    )
    return TableContract(
        name=expectation.name,
        columns=tuple(
            ColumnContract(
                name=column.name,
                data_type=column.data_type,
                is_nullable=column.nullable,
                column_default=None,
            )
            for column in expectation.columns
        ),
        constraints=tuple(constraints),
        indexes=tuple(
            IndexContract(
                name=name,
                definition=f"CREATE INDEX {name}",
                is_unique=False,
                is_primary=False,
            )
            for name in expectation.index_names
        ),
    )


def _valid_schema() -> tuple[dict[str, TableContract], dict[str, str]]:
    contracts = {
        expectation.name: _contract_from(expectation) for expectation in EXPECTED_TABLES
    }
    views = {view.name: " ".join(view.fragments) for view in EXPECTED_VIEWS}
    return contracts, views


def _violation_targets(violations: tuple[SchemaViolation, ...]) -> list[str]:
    return [violation.target for violation in violations]


@pytest.mark.unit
def test_matching_schema_produces_no_violations() -> None:
    contracts, views = _valid_schema()

    assert validate_schema(contracts, views) == ()


@pytest.mark.unit
def test_missing_and_unexpected_tables_are_reported() -> None:
    contracts, views = _valid_schema()
    contracts.pop("users")
    contracts["legacy_orders"] = _contract_from(EXPECTED_TABLES[0])

    violations = validate_schema(contracts, views)

    assert _violation_targets(violations) == ["legacy_orders", "users"]
    assert [violation.message for violation in violations] == [
        "unexpected table in schema 'public'",
        "table is missing",
    ]


@pytest.mark.unit
def test_column_type_and_nullability_drift_are_reported() -> None:
    contracts, views = _valid_schema()
    catalog = contracts["catalog_items"]
    contracts["catalog_items"] = replace(
        catalog,
        columns=tuple(
            replace(column, data_type="text")
            if column.name == "price_cents"
            else replace(column, is_nullable=True)
            if column.name == "sku"
            else column
            for column in catalog.columns
        ),
    )

    violations = validate_schema(contracts, views)

    assert _violation_targets(violations) == [
        "catalog_items.sku",
        "catalog_items.price_cents",
    ]
    assert violations[0].message == "expected NOT NULL"
    assert violations[1].message == "expected type 'integer', found 'text'"


@pytest.mark.unit
def test_missing_constraints_and_indexes_are_reported() -> None:
    contracts, views = _valid_schema()
    catalog = contracts["catalog_items"]
    contracts["catalog_items"] = replace(
        catalog,
        constraints=tuple(
            constraint
            for constraint in catalog.constraints
            if constraint.name != "catalog_items_status_check"
        ),
        indexes=(),
    )

    violations = validate_schema(contracts, views)
    targets = _violation_targets(violations)

    assert targets == [
        "catalog_items_status_check",
        "idx_catalog_items_workspace_status",
    ]


@pytest.mark.unit
def test_missing_constraint_fragments_are_reported() -> None:
    contracts, views = _valid_schema()
    catalog = contracts["catalog_items"]
    contracts["catalog_items"] = replace(
        catalog,
        constraints=tuple(
            constraint
            for constraint in catalog.constraints
            if not constraint.name.startswith("fragment_")
        ),
        indexes=catalog.indexes,
    )

    violations = validate_schema(contracts, views)

    assert _violation_targets(violations) == ["catalog_items"] * 4
    first_fragment = EXPECTED_TABLES[2].constraint_fragments[0]
    assert violations[0].message == (
        f"no constraint definition contains {first_fragment!r}"
    )


@pytest.mark.unit
def test_missing_views_and_view_fragments_are_reported() -> None:
    contracts, views = _valid_schema()
    views["workspace_catalog_summary"] = "SELECT 1"
    views["legacy_report"] = "SELECT 1"

    violations = validate_schema(contracts, views)
    fragment_count = len(EXPECTED_VIEWS[0].fragments)

    assert _violation_targets(violations) == ["legacy_report"] + (
        ["workspace_catalog_summary"] * fragment_count
    )
    assert violations[0].message == "unexpected view in schema 'public'"


@pytest.mark.unit
def test_table_contract_lookup_helpers_and_kind_filter() -> None:
    contract = _contract_from(EXPECTED_TABLES[0])

    assert contract.column_names == ("id", "slug", "name", "created_at")
    assert contract.column("slug") is not None
    assert contract.column("missing") is None
    assert contract.constraint("workspaces_pkey") is not None
    assert contract.constraint("missing") is None
    assert contract.constraint_definitions("primary_key") == ()
    assert contract.constraint_definitions() == (
        "",
        "",
        "PRIMARY KEY (id)",
        "UNIQUE (slug)",
    )
