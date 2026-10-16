"""Explicit transaction semantics against the local PostgreSQL test database."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import allure
import psycopg
import pytest
from qa_core.data_factories import NamespaceIdentity
from qa_core.db import DatabaseClient

from tests.integration.conftest import ConnectionFactory


def _insert_item(
    client: DatabaseClient,
    workspace_id: int,
    sku: str,
    *,
    price_cents: int = 100,
) -> int:
    row = client.fetch_one(
        """
        INSERT INTO catalog_items (workspace_id, sku, name, price_cents)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (workspace_id, sku, f"Item {sku}", price_cents),
    )
    if row is None:
        raise RuntimeError("insert returned no row")
    return int(row["id"])


def _count_items(client: DatabaseClient, workspace_id: int) -> int:
    row = client.fetch_one(
        "SELECT COUNT(*) AS items FROM catalog_items WHERE workspace_id = %s",
        (workspace_id,),
    )
    if row is None:
        raise RuntimeError("count query returned no row")
    return int(row["items"])


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Transactions")
@pytest.mark.integration
def test_autocommit_write_is_visible_to_a_second_connection(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    reader = connection_factory.open(application_name="qa-week9-reader")

    assert _count_items(reader, db_namespace.workspace_id) == 2
    _insert_item(database, db_namespace.workspace_id, "TX-AUTO-1")

    assert _count_items(reader, db_namespace.workspace_id) == 3


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Transactions")
@pytest.mark.integration
def test_uncommitted_write_stays_invisible_until_commit(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    writer = connection_factory.open(application_name="qa-week9-writer")

    _insert_item(writer, db_namespace.workspace_id, "TX-PENDING-1")
    assert writer.transaction_status == "INTRANS"
    assert _count_items(writer, db_namespace.workspace_id) == 3
    assert _count_items(database, db_namespace.workspace_id) == 2

    writer.commit()

    assert writer.transaction_status == "IDLE"
    assert _count_items(database, db_namespace.workspace_id) == 3


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Transactions")
@pytest.mark.integration
def test_rollback_discards_every_statement_of_the_transaction(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    writer = connection_factory.open(application_name="qa-week9-rollback")

    _insert_item(writer, db_namespace.workspace_id, "TX-ROLLBACK-1")
    _insert_item(writer, db_namespace.workspace_id, "TX-ROLLBACK-2")
    writer.rollback()

    assert writer.transaction_status == "IDLE"
    assert _count_items(writer, db_namespace.workspace_id) == 2
    assert _count_items(database, db_namespace.workspace_id) == 2


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Transactions")
@pytest.mark.integration
def test_savepoint_rolls_back_only_the_marked_part(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    writer = connection_factory.open(application_name="qa-week9-savepoint")

    _insert_item(writer, db_namespace.workspace_id, "TX-SAVEPOINT-KEEP")
    writer.execute("SAVEPOINT before_second_item")
    _insert_item(writer, db_namespace.workspace_id, "TX-SAVEPOINT-DROP")
    writer.execute("ROLLBACK TO SAVEPOINT before_second_item")
    _insert_item(writer, db_namespace.workspace_id, "TX-SAVEPOINT-AFTER")
    writer.commit()

    skus = [
        str(row["sku"])
        for row in database.fetch_all(
            """
            SELECT sku FROM catalog_items
            WHERE workspace_id = %s AND starts_with(sku, 'TX-SAVEPOINT')
            ORDER BY sku
            """,
            (db_namespace.workspace_id,),
        )
    ]
    assert skus == ["TX-SAVEPOINT-AFTER", "TX-SAVEPOINT-KEEP"]


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Transactions")
@pytest.mark.integration
def test_unique_violation_puts_the_transaction_in_error_until_rollback(
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    writer = connection_factory.open(application_name="qa-week9-failed-tx")
    sku = "TX-FAILED-1"
    _insert_item(writer, db_namespace.workspace_id, sku)

    with pytest.raises(psycopg.errors.UniqueViolation) as error:
        _insert_item(writer, db_namespace.workspace_id, sku)

    assert error.value.sqlstate == "23505"
    assert writer.transaction_status == "INERROR"
    with pytest.raises(psycopg.errors.InFailedSqlTransaction):
        _count_items(writer, db_namespace.workspace_id)

    writer.rollback()

    assert writer.transaction_status == "IDLE"
    assert _count_items(writer, db_namespace.workspace_id) == 2
    _insert_item(writer, db_namespace.workspace_id, "TX-FAILED-2")
    writer.commit()
    assert _count_items(writer, db_namespace.workspace_id) == 3


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Transactions")
@pytest.mark.integration
def test_transaction_context_manager_commits_and_rolls_back(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    writer = connection_factory.open(application_name="qa-week9-context")

    with writer.transaction():
        _insert_item(writer, db_namespace.workspace_id, "TX-CONTEXT-COMMIT")
    assert _count_items(database, db_namespace.workspace_id) == 3

    with pytest.raises(RuntimeError, match="business failure"):
        with writer.transaction():
            _insert_item(writer, db_namespace.workspace_id, "TX-CONTEXT-ROLLBACK")
            raise RuntimeError("business failure")
    assert _count_items(database, db_namespace.workspace_id) == 3


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Isolation levels")
@pytest.mark.integration
def test_isolation_level_is_read_committed_by_default(
    database: DatabaseClient,
    connection_factory: ConnectionFactory,
) -> None:
    assert database.setting("transaction_isolation") == "read committed"

    serializable = connection_factory.open(isolation_level="serializable")
    assert serializable.isolation_level == "serializable"
    assert serializable.setting("transaction_isolation") == "serializable"


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Isolation levels")
@pytest.mark.integration
def test_isolation_level_cannot_change_inside_an_open_transaction(
    connection_factory: ConnectionFactory,
) -> None:
    client = connection_factory.open(isolation_level="repeatable_read")
    client.fetch_one("SELECT 1 AS one")
    assert client.transaction_status == "INTRANS"

    with pytest.raises(RuntimeError, match="inside a transaction"):
        client.set_isolation_level("serializable")

    client.rollback()
    client.set_isolation_level("serializable")
    assert client.isolation_level == "serializable"
