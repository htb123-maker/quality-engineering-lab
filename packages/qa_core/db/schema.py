"""Read-only PostgreSQL schema introspection and schema-contract checks.

The local SUT schema is created by ``apps/compose/postgres/init/001_schema.sql``
when the Compose volume is first initialised. That script is not a migration
tool: it never changes a database that already exists. Week 9 therefore treats
the schema as an external contract and verifies it read-only, so a drifted
database fails a gate instead of silently invalidating every database test.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from qa_core.db.client import DatabaseClient

CONSTRAINT_KINDS = {
    "p": "primary_key",
    "f": "foreign_key",
    "u": "unique",
    "c": "check",
    "x": "exclusion",
}


@dataclass(frozen=True)
class ColumnContract:
    """One column as reported by ``information_schema.columns``."""

    name: str
    data_type: str
    is_nullable: bool
    column_default: str | None


@dataclass(frozen=True)
class ConstraintContract:
    """One constraint with the definition PostgreSQL prints for it."""

    name: str
    kind: str
    definition: str


@dataclass(frozen=True)
class IndexContract:
    """One index as reported by ``pg_indexes``/``pg_index``."""

    name: str
    definition: str
    is_unique: bool
    is_primary: bool


@dataclass(frozen=True)
class TableContract:
    """The observable shape of one table: columns, constraints, and indexes."""

    name: str
    columns: tuple[ColumnContract, ...]
    constraints: tuple[ConstraintContract, ...]
    indexes: tuple[IndexContract, ...]

    @property
    def column_names(self) -> tuple[str, ...]:
        """Return column names in ordinal order."""

        return tuple(column.name for column in self.columns)

    def column(self, name: str) -> ColumnContract | None:
        """Return one column contract by name."""

        for column in self.columns:
            if column.name == name:
                return column
        return None

    def constraint(self, name: str) -> ConstraintContract | None:
        """Return one constraint contract by name."""

        for constraint in self.constraints:
            if constraint.name == name:
                return constraint
        return None

    def index(self, name: str) -> IndexContract | None:
        """Return one index contract by name."""

        for index in self.indexes:
            if index.name == name:
                return index
        return None

    def constraint_definitions(self, kind: str | None = None) -> tuple[str, ...]:
        """Return constraint definitions, optionally filtered by kind."""

        return tuple(
            constraint.definition
            for constraint in self.constraints
            if kind is None or constraint.kind == kind
        )


def list_tables(db: DatabaseClient) -> tuple[str, ...]:
    """Return ordinary tables in the ``public`` schema."""

    rows = db.fetch_all(
        """
        SELECT c.relname AS name
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
        ORDER BY c.relname
        """
    )
    return tuple(str(row["name"]) for row in rows)


def list_views(db: DatabaseClient) -> tuple[str, ...]:
    """Return views in the ``public`` schema."""

    rows = db.fetch_all(
        """
        SELECT c.relname AS name
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'v'
        ORDER BY c.relname
        """
    )
    return tuple(str(row["name"]) for row in rows)


def view_definition(db: DatabaseClient, view: str) -> str:
    """Return the stored ``SELECT`` text of one view."""

    row = db.fetch_one(
        """
        SELECT pg_get_viewdef(c.oid, true) AS definition
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'v' AND c.relname = %s
        """,
        (view,),
    )
    if row is None:
        raise LookupError(f"view {view!r} does not exist in schema 'public'")
    return str(row["definition"])


def table_contract(db: DatabaseClient, table: str) -> TableContract:
    """Return the full read-only contract for one table."""

    column_rows = db.fetch_all(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    if not column_rows:
        raise LookupError(f"table {table!r} does not exist in schema 'public'")

    constraint_rows = db.fetch_all(
        """
        SELECT c.conname AS name,
               c.contype AS kind,
               pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint AS c
        JOIN pg_class AS t ON t.oid = c.conrelid
        JOIN pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public' AND t.relname = %s
        ORDER BY c.conname
        """,
        (table,),
    )

    index_rows = db.fetch_all(
        """
        SELECT i.relname AS name,
               pg_get_indexdef(x.indexrelid) AS definition,
               x.indisunique AS is_unique,
               x.indisprimary AS is_primary
        FROM pg_index AS x
        JOIN pg_class AS i ON i.oid = x.indexrelid
        JOIN pg_class AS t ON t.oid = x.indrelid
        JOIN pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public' AND t.relname = %s
        ORDER BY i.relname
        """,
        (table,),
    )

    return TableContract(
        name=table,
        columns=tuple(
            ColumnContract(
                name=str(row["column_name"]),
                data_type=str(row["data_type"]),
                is_nullable=str(row["is_nullable"]).upper() == "YES",
                column_default=(
                    None
                    if row["column_default"] is None
                    else str(row["column_default"])
                ),
            )
            for row in column_rows
        ),
        constraints=tuple(
            ConstraintContract(
                name=str(row["name"]),
                kind=CONSTRAINT_KINDS.get(str(row["kind"]), str(row["kind"])),
                definition=str(row["definition"]),
            )
            for row in constraint_rows
        ),
        indexes=tuple(
            IndexContract(
                name=str(row["name"]),
                definition=str(row["definition"]),
                is_unique=bool(row["is_unique"]),
                is_primary=bool(row["is_primary"]),
            )
            for row in index_rows
        ),
    )


def schema_contract(
    db: DatabaseClient,
    tables: tuple[str, ...] | None = None,
) -> dict[str, TableContract]:
    """Return the contract for every requested table, defaulting to all tables."""

    selected = tables if tables is not None else list_tables(db)
    return {table: table_contract(db, table) for table in selected}


@dataclass(frozen=True)
class ColumnExpectation:
    """One required column with its type and nullability."""

    name: str
    data_type: str
    nullable: bool = False


@dataclass(frozen=True)
class TableExpectation:
    """Required shape of one table."""

    name: str
    columns: tuple[ColumnExpectation, ...]
    constraint_names: tuple[str, ...] = ()
    constraint_fragments: tuple[str, ...] = ()
    index_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ViewExpectation:
    """Required shape of one view, matched on definition fragments."""

    name: str
    fragments: tuple[str, ...]


@dataclass(frozen=True)
class SchemaViolation:
    """One drift between the live schema and the expected contract."""

    target: str
    message: str


# Expected public schema of the local SUT, mirroring
# apps/compose/postgres/init/001_schema.sql. Update this contract in the same
# change as the init script; that is the whole point of the read-only check.
EXPECTED_TABLES: tuple[TableExpectation, ...] = (
    TableExpectation(
        name="workspaces",
        columns=(
            ColumnExpectation("id", "bigint"),
            ColumnExpectation("slug", "text"),
            ColumnExpectation("name", "text"),
            ColumnExpectation("created_at", "timestamp with time zone"),
        ),
        constraint_names=("workspaces_pkey", "workspaces_slug_key"),
        constraint_fragments=(
            "PRIMARY KEY (id)",
            "UNIQUE (slug)",
        ),
    ),
    TableExpectation(
        name="users",
        columns=(
            ColumnExpectation("id", "bigint"),
            ColumnExpectation("workspace_id", "bigint"),
            ColumnExpectation("email", "text"),
            ColumnExpectation("display_name", "text"),
            ColumnExpectation("role", "text"),
            ColumnExpectation("status", "text"),
            ColumnExpectation("created_at", "timestamp with time zone"),
        ),
        constraint_names=(
            "users_pkey",
            "users_workspace_id_fkey",
            "users_workspace_id_email_key",
            "users_role_check",
            "users_status_check",
        ),
        constraint_fragments=(
            "FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE",
            "UNIQUE (workspace_id, email)",
            "role = ANY",
            "status = ANY",
        ),
        index_names=("idx_users_workspace_id",),
    ),
    TableExpectation(
        name="catalog_items",
        columns=(
            ColumnExpectation("id", "bigint"),
            ColumnExpectation("workspace_id", "bigint"),
            ColumnExpectation("sku", "text"),
            ColumnExpectation("name", "text"),
            ColumnExpectation("price_cents", "integer"),
            ColumnExpectation("status", "text"),
            ColumnExpectation("created_at", "timestamp with time zone"),
        ),
        constraint_names=(
            "catalog_items_pkey",
            "catalog_items_workspace_id_fkey",
            "catalog_items_workspace_id_sku_key",
            "catalog_items_price_cents_check",
            "catalog_items_status_check",
        ),
        constraint_fragments=(
            "FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE",
            "UNIQUE (workspace_id, sku)",
            "price_cents >= 0",
            "status = ANY",
        ),
        index_names=("idx_catalog_items_workspace_status",),
    ),
)

EXPECTED_VIEWS: tuple[ViewExpectation, ...] = (
    ViewExpectation(
        name="workspace_catalog_summary",
        fragments=(
            "workspaces",
            "catalog_items",
            "item_count",
            "catalog_value_cents",
            "status = 'active'",
        ),
    ),
)


def _check_table(
    contract: TableContract,
    expectation: TableExpectation,
) -> list[SchemaViolation]:
    violations: list[SchemaViolation] = []
    for column in expectation.columns:
        actual = contract.column(column.name)
        if actual is None:
            violations.append(
                SchemaViolation(
                    f"{expectation.name}.{column.name}",
                    "column is missing",
                )
            )
            continue
        if actual.data_type != column.data_type:
            violations.append(
                SchemaViolation(
                    f"{expectation.name}.{column.name}",
                    f"expected type {column.data_type!r}, found {actual.data_type!r}",
                )
            )
        if actual.is_nullable != column.nullable:
            expected = "NULL" if column.nullable else "NOT NULL"
            violations.append(
                SchemaViolation(
                    f"{expectation.name}.{column.name}",
                    f"expected {expected}",
                )
            )

    for name in expectation.constraint_names:
        if contract.constraint(name) is None:
            violations.append(
                SchemaViolation(name, f"constraint is missing on {expectation.name}")
            )

    definitions = contract.constraint_definitions()
    for fragment in expectation.constraint_fragments:
        if not any(fragment in definition for definition in definitions):
            violations.append(
                SchemaViolation(
                    expectation.name,
                    f"no constraint definition contains {fragment!r}",
                )
            )

    for name in expectation.index_names:
        if contract.index(name) is None:
            violations.append(
                SchemaViolation(name, f"index is missing on {expectation.name}")
            )
    return violations


def check_schema_contract(
    db: DatabaseClient,
    *,
    tables: tuple[TableExpectation, ...] = EXPECTED_TABLES,
    views: tuple[ViewExpectation, ...] = EXPECTED_VIEWS,
) -> tuple[SchemaViolation, ...]:
    """Read the live schema and compare it against the expected contract."""

    contracts = {name: table_contract(db, name) for name in list_tables(db)}
    definitions = {name: view_definition(db, name) for name in list_views(db)}
    return validate_schema(contracts, definitions, tables=tables, views=views)


def validate_schema(
    contracts: Mapping[str, TableContract],
    view_definitions: Mapping[str, str],
    *,
    tables: tuple[TableExpectation, ...] = EXPECTED_TABLES,
    views: tuple[ViewExpectation, ...] = EXPECTED_VIEWS,
) -> tuple[SchemaViolation, ...]:
    """Compare already-read schema facts against the expected contract.

    Missing tables, drifted columns, missing constraints or indexes, drifted
    views, and unexpected extra tables all count as violations so that schema
    changes are always deliberate. Keeping this pure makes the comparison
    rule-set unit-testable without a database.
    """

    violations: list[SchemaViolation] = []
    expected_names = {expectation.name for expectation in tables}
    for name in sorted(set(contracts) - expected_names):
        violations.append(
            SchemaViolation(name, "unexpected table in schema 'public'")
        )
    for expectation in tables:
        contract = contracts.get(expectation.name)
        if contract is None:
            violations.append(
                SchemaViolation(expectation.name, "table is missing")
            )
            continue
        violations.extend(_check_table(contract, expectation))

    expected_view_names = {view.name for view in views}
    for name in sorted(set(view_definitions) - expected_view_names):
        violations.append(
            SchemaViolation(name, "unexpected view in schema 'public'")
        )
    for view in views:
        definition = view_definitions.get(view.name)
        if definition is None:
            violations.append(SchemaViolation(view.name, "view is missing"))
            continue
        for fragment in view.fragments:
            if fragment not in definition:
                violations.append(
                    SchemaViolation(
                        view.name,
                        f"view definition does not contain {fragment!r}",
                    )
                )

    return tuple(violations)
