"""Row-lock waits, blocking-pair evidence, and a real deadlock."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import threading
import time

import allure
import psycopg
import pytest
from qa_core.data_factories import NamespaceIdentity
from qa_core.db import (
    DatabaseClient,
    active_waits,
    blocking_pairs,
    deadlock_count,
    wait_for_blocking_pair,
)

from tests.integration.conftest import ConnectionFactory


def _item_ids(database: DatabaseClient, workspace_id: int) -> list[int]:
    rows = database.fetch_all(
        """
        SELECT id FROM catalog_items
        WHERE workspace_id = %s ORDER BY id
        """,
        (workspace_id,),
    )
    return [int(row["id"]) for row in rows]


def _item_names(database: DatabaseClient, workspace_id: int) -> list[str]:
    rows = database.fetch_all(
        """
        SELECT name FROM catalog_items
        WHERE workspace_id = %s ORDER BY id
        """,
        (workspace_id,),
    )
    return [str(row["name"]) for row in rows]


def _lock_rows(client: DatabaseClient, item_id: int, name: str) -> None:
    client.execute(
        "UPDATE catalog_items SET name = %s WHERE id = %s",
        (name, item_id),
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Row locks")
@pytest.mark.integration
def test_row_lock_blocks_a_second_writer_and_reports_the_blocking_pair(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    holder = connection_factory.open(application_name="qa-week9-lock-holder")
    waiter = connection_factory.open(application_name="qa-week9-lock-waiter")
    watcher = connection_factory.open(
        autocommit=True, application_name="qa-week9-lock-watcher"
    )
    item_id = _item_ids(database, db_namespace.workspace_id)[0]

    _lock_rows(holder, item_id, "Held by the first writer")
    waiter.execute("SET lock_timeout = 10000")
    outcome: dict[str, str] = {}

    def run_waiter() -> None:
        try:
            _lock_rows(waiter, item_id, "Written by the second writer")
            outcome["status"] = "granted"
        except Exception as exc:  # noqa: BLE001 - the outcome is the assertion
            outcome["status"] = type(exc).__name__

    thread = threading.Thread(target=run_waiter, daemon=True)
    thread.start()
    try:
        pair = wait_for_blocking_pair(
            watcher,
            blocked_pid=waiter.pid,
            blocking_pid=holder.pid,
            timeout=5.0,
        )
        still_waiting = outcome == {}
    finally:
        holder.commit()
        thread.join(timeout=10)

    allure.attach(
        "\n".join(
            (
                f"blocked pid: {pair.blocked_pid}",
                f"blocking pid: {pair.blocking_pid}",
                f"wait event: {pair.wait_event_type}/{pair.wait_event}",
                f"blocked mode / blocking mode: {pair.blocked_mode} / {pair.blocking_mode}",
                f"blocked statement: {pair.blocked_query.strip()}",
            )
        ),
        name="pg_locks blocking pair",
        attachment_type=allure.attachment_type.TEXT,
    )

    assert still_waiting, "the second writer completed while the row lock was held"
    assert pair.wait_event_type == "Lock"
    assert pair.blocked_mode == "ShareLock"
    assert pair.blocking_mode == "ExclusiveLock"
    assert not thread.is_alive()
    assert outcome["status"] == "granted"


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Row locks")
@pytest.mark.integration
def test_nowait_lock_attempt_fails_fast_with_sqlstate_55p03(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    holder = connection_factory.open(application_name="qa-week9-nowait-holder")
    contender = connection_factory.open(application_name="qa-week9-nowait")
    item_id = _item_ids(database, db_namespace.workspace_id)[0]

    _lock_rows(holder, item_id, "Held while the contender gives up")

    with pytest.raises(psycopg.errors.LockNotAvailable) as error:
        contender.fetch_one(
            "SELECT id FROM catalog_items WHERE id = %s FOR UPDATE NOWAIT",
            (item_id,),
        )

    assert error.value.sqlstate == "55P03"
    holder.rollback()


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Deadlocks")
@pytest.mark.integration
def test_opposite_update_order_deadlocks_and_one_transaction_is_rolled_back(
    database: DatabaseClient,
    db_namespace: NamespaceIdentity,
    connection_factory: ConnectionFactory,
) -> None:
    workspace_id = db_namespace.workspace_id
    first_id, second_id = _item_ids(database, workspace_id)[:2]
    before = deadlock_count(database)
    first = connection_factory.open(application_name="qa-week9-deadlock-a")
    second = connection_factory.open(application_name="qa-week9-deadlock-b")
    barrier = threading.Barrier(2, timeout=10)
    outcomes: dict[str, str] = {}
    details: dict[str, str] = {}

    def run(
        name: str,
        client: DatabaseClient,
        own_item: int,
        other_item: int,
    ) -> None:
        try:
            _lock_rows(client, own_item, f"{name}-first")
            barrier.wait()
            time.sleep(0.4)
            _lock_rows(client, other_item, f"{name}-second")
            client.commit()
            outcomes[name] = "committed"
        except psycopg.errors.DeadlockDetected as exc:
            client.rollback()
            outcomes[name] = f"deadlock:{exc.sqlstate}"
            details[name] = str(exc)
        except Exception as exc:  # noqa: BLE001 - record and assert below
            client.rollback()
            outcomes[name] = f"error:{type(exc).__name__}"
            details[name] = str(exc)

    thread_a = threading.Thread(
        target=run,
        args=("a", first, first_id, second_id),
        daemon=True,
    )
    thread_b = threading.Thread(
        target=run,
        args=("b", second, second_id, first_id),
        daemon=True,
    )
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=20)
    thread_b.join(timeout=20)
    after = deadlock_count(database)
    names = _item_names(database, workspace_id)

    allure.attach(
        "\n".join(
            (
                f"outcomes: {outcomes}",
                f"deadlocks before/after: {before}/{after}",
                *(f"{name} error: {text}" for name, text in sorted(details.items())),
            )
        ),
        name="Deadlock evidence",
        attachment_type=allure.attachment_type.TEXT,
    )

    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert sorted(outcomes.values()) == ["committed", "deadlock:40P01"]
    assert after == before + 1
    assert sorted(names) in (
        ["a-first", "a-second"],
        ["b-first", "b-second"],
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("Database")
@allure.story("Locks at rest")
@pytest.mark.integration
def test_no_session_is_left_waiting_on_a_lock(database: DatabaseClient) -> None:
    waits = active_waits(database)
    pairs = blocking_pairs(database)

    assert waits == 0
    assert pairs == ()
