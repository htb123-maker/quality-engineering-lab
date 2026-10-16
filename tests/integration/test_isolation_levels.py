"""Observable isolation-level behaviour: visibility, snapshots, and retries."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import allure
import psycopg
import pytest
from qa_core.data_factories import NamespaceIdentity
from qa_core.db import DatabaseClient

from tests.integration.conftest import ConnectionFactory


def _first_item_id(database: DatabaseClient, workspace_id: int) -> int:
    row = database.fetch_one(
        """
        SELECT id FROM catalog_items
        WHERE workspace_id = %s ORDER BY id LIMIT 1
        """,
        (workspace_id,),
    )
    if row is None:
        raise RuntimeError("namespace fixture seeded no catalog item")
    return int(row["id"])


def _item_name(client: DatabaseClient, item_id: int) -> str:
    row = client.fetch_one(
        "SELECT name FROM catalog_items WHERE id = %s",
        (item_id,),
    )
    if row is None:
        raise RuntimeError(f"catalog item {item_id} disappeared")
    return str(row["name"])


def _item_count(client: DatabaseClient, workspace_id: int) -> int:
    row = client.fetch_one(
        "SELECT COUNT(*) AS items FROM catalog_items WHERE workspace_id = %s",
        (workspace_id,),
    )
    if row is None:
        raise RuntimeError("count query returned no row")
    return int(row["items"])


def _insert_item(client: DatabaseClient, workspace_id: int, sku: str) -> None:
    client.execute(
        """
        INSERT INTO catalog_items (workspace_id, sku, name, price_cents)
        VALUES (%s, %s, %s, %s)
        """,
        (workspace_id, sku, f"Item {sku}", 250),
    )


def _attach_visibility(name: str, payload: dict[str, object]) -> None:
    allure.attach(
        "\n".join(f"{key}: {value}" for key, value in payload.items()),
        name=name,
        attachment_type=allure.attachment_type.TEXT,
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Read Committed")
@pytest.mark.integration
def test_read_committed_sees_each_commit_inside_one_transaction(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    reader = connection_factory.open(isolation_level="read_committed")
    writer = connection_factory.open()
    item_id = _first_item_id(database, db_namespace.workspace_id)

    before = _item_name(reader, item_id)
    writer.execute(
        "UPDATE catalog_items SET name = %s WHERE id = %s",
        ("Changed by another session", item_id),
    )
    writer.commit()
    after = _item_name(reader, item_id)
    reader.rollback()

    _attach_visibility(
        "Read Committed non-repeatable read",
        {
            "isolation": "read committed",
            "first read": before,
            "second read": after,
        },
    )
    assert before != after
    assert after == "Changed by another session"


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Read Committed")
@pytest.mark.integration
def test_read_committed_sees_rows_inserted_after_the_transaction_started(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    reader = connection_factory.open(isolation_level="read_committed")
    writer = connection_factory.open()

    before = _item_count(reader, db_namespace.workspace_id)
    _insert_item(writer, db_namespace.workspace_id, "ISO-RC-PHANTOM")
    writer.commit()
    after = _item_count(reader, db_namespace.workspace_id)
    reader.rollback()

    assert (before, after) == (2, 3)


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("No dirty reads")
@pytest.mark.integration
def test_uncommitted_updates_are_never_visible_to_other_sessions(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    reader = connection_factory.open(isolation_level="read_committed")
    writer = connection_factory.open()
    item_id = _first_item_id(database, db_namespace.workspace_id)
    original = _item_name(database, item_id)

    writer.execute(
        "UPDATE catalog_items SET name = %s WHERE id = %s",
        ("Uncommitted rewrite", item_id),
    )
    during = _item_name(reader, item_id)
    assert during == original

    writer.rollback()
    after_rollback = _item_name(reader, item_id)
    reader.rollback()

    assert during == original
    assert after_rollback == original


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Repeatable Read")
@pytest.mark.integration
def test_repeatable_read_keeps_one_snapshot_for_the_whole_transaction(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    reader = connection_factory.open(isolation_level="repeatable_read")
    writer = connection_factory.open()
    item_id = _first_item_id(database, db_namespace.workspace_id)
    original = _item_name(database, item_id)

    first_read = _item_name(reader, item_id)
    first_count = _item_count(reader, db_namespace.workspace_id)

    writer.execute(
        "UPDATE catalog_items SET name = %s WHERE id = %s",
        ("Changed while the snapshot was open", item_id),
    )
    _insert_item(writer, db_namespace.workspace_id, "ISO-RR-HIDDEN")
    writer.commit()

    second_read = _item_name(reader, item_id)
    second_count = _item_count(reader, db_namespace.workspace_id)
    reader.rollback()

    _attach_visibility(
        "Repeatable Read snapshot",
        {
            "isolation": reader.setting("transaction_isolation"),
            "first read": first_read,
            "second read": second_read,
            "first count": first_count,
            "second count": second_count,
        },
    )
    assert first_read == second_read == original
    assert first_count == second_count == 2


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Repeatable Read")
@pytest.mark.integration
def test_repeatable_read_update_after_a_concurrent_commit_asks_for_a_retry(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    reader = connection_factory.open(isolation_level="repeatable_read")
    writer = connection_factory.open()
    item_id = _first_item_id(database, db_namespace.workspace_id)

    reader.fetch_one("SELECT id FROM catalog_items WHERE id = %s", (item_id,))
    writer.execute(
        "UPDATE catalog_items SET name = %s WHERE id = %s",
        ("Committed before the conflicting update", item_id),
    )
    writer.commit()

    with pytest.raises(psycopg.errors.SerializationFailure) as error:
        reader.execute(
            "UPDATE catalog_items SET name = %s WHERE id = %s",
            ("Conflicting update", item_id),
        )

    _attach_visibility(
        "Repeatable Read serialization failure",
        {
            "sqlstate": error.value.sqlstate or "",
            "message": str(error.value).splitlines()[0],
        },
    )
    assert error.value.sqlstate == "40001"
    assert "could not serialize access" in str(error.value)
    reader.rollback()
    assert _item_name(database, item_id) == "Committed before the conflicting update"


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Serializable")
@pytest.mark.integration
def test_serializable_update_after_a_concurrent_commit_asks_for_a_retry(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    reader = connection_factory.open(isolation_level="serializable")
    writer = connection_factory.open()
    item_id = _first_item_id(database, db_namespace.workspace_id)

    reader.fetch_one("SELECT id FROM catalog_items WHERE id = %s", (item_id,))
    writer.execute(
        "UPDATE catalog_items SET name = %s WHERE id = %s",
        ("Serializable writer", item_id),
    )
    writer.commit()

    with pytest.raises(psycopg.errors.SerializationFailure) as error:
        reader.execute(
            "UPDATE catalog_items SET name = %s WHERE id = %s",
            ("Serializable loser", item_id),
        )

    assert error.value.sqlstate == "40001"
    reader.rollback()


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("No dirty reads")
@pytest.mark.integration
def test_read_uncommitted_never_returns_a_dirty_row(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    reader = connection_factory.open(autocommit=True, application_name="qa-ru-reader")
    writer = connection_factory.open()
    item_id = _first_item_id(database, db_namespace.workspace_id)
    original = _item_name(database, item_id)
    original_count = _item_count(database, db_namespace.workspace_id)

    reader.execute(
        "SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL READ UNCOMMITTED"
    )
    # PostgreSQL accepts the level but documents that it behaves like Read
    # Committed, so the observable guarantee to check is "no dirty rows".
    assert reader.setting("transaction_isolation") == "read uncommitted"

    writer.execute(
        "UPDATE catalog_items SET name = %s WHERE id = %s",
        ("Dirty candidate", item_id),
    )
    _insert_item(writer, db_namespace.workspace_id, "ISO-RU-DIRTY")

    during = _item_name(reader, item_id)
    during_count = _item_count(reader, db_namespace.workspace_id)

    _attach_visibility(
        "Read Uncommitted dirty read check",
        {
            "session level": reader.setting("transaction_isolation"),
            "name during uncommitted update": during,
            "count during uncommitted insert": during_count,
        },
    )
    assert during == original
    assert during_count == original_count

    writer.rollback()
    assert _item_name(reader, item_id) == original
