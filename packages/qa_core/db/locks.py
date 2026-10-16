"""Read-only lock introspection for concurrency and deadlock tests.

``pg_locks`` alone only says "this pid is waiting". Joining it with
``pg_stat_activity`` twice turns the snapshot into an answer to the question a
tester actually asks: *who* is blocking *whom*, on which relation, and in which
lock mode.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from qa_core.db.client import DatabaseClient


@dataclass(frozen=True)
class LockWait:
    """One blocked/blocking pair from ``pg_locks`` and ``pg_stat_activity``."""

    blocked_pid: int
    blocking_pid: int
    blocked_query: str
    blocking_query: str
    lock_type: str
    blocked_mode: str
    blocking_mode: str
    relation: str | None
    wait_event_type: str | None
    wait_event: str | None


def blocking_pairs(db: DatabaseClient) -> tuple[LockWait, ...]:
    """Return every lock wait visible in the current database."""

    rows = db.fetch_all(
        """
        SELECT
            blocked.pid AS blocked_pid,
            blocking.pid AS blocking_pid,
            blocked.query AS blocked_query,
            blocking.query AS blocking_query,
            blocked_locks.locktype AS lock_type,
            blocked_locks.mode AS blocked_mode,
            blocking_locks.mode AS blocking_mode,
            CASE
                WHEN blocked_locks.relation IS NULL THEN NULL
                ELSE blocked_locks.relation::regclass::text
            END AS relation,
            blocked.wait_event_type AS wait_event_type,
            blocked.wait_event AS wait_event
        FROM pg_stat_activity AS blocked
        JOIN pg_locks AS blocked_locks
            ON blocked_locks.pid = blocked.pid AND NOT blocked_locks.granted
        JOIN pg_locks AS blocking_locks
            ON blocking_locks.locktype = blocked_locks.locktype
           AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
           AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
           AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
           AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
           AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
           AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
           AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
           AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
           AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
           AND blocking_locks.pid <> blocked_locks.pid
           AND blocking_locks.granted
        JOIN pg_stat_activity AS blocking ON blocking.pid = blocking_locks.pid
        ORDER BY blocked.pid, blocking.pid
        """
    )
    return tuple(
        LockWait(
            blocked_pid=int(row["blocked_pid"]),
            blocking_pid=int(row["blocking_pid"]),
            blocked_query=str(row["blocked_query"]),
            blocking_query=str(row["blocking_query"]),
            lock_type=str(row["lock_type"]),
            blocked_mode=str(row["blocked_mode"]),
            blocking_mode=str(row["blocking_mode"]),
            relation=None if row["relation"] is None else str(row["relation"]),
            wait_event_type=(
                None
                if row["wait_event_type"] is None
                else str(row["wait_event_type"])
            ),
            wait_event=None if row["wait_event"] is None else str(row["wait_event"]),
        )
        for row in rows
    )


def wait_for_blocking_pair(
    db: DatabaseClient,
    *,
    blocked_pid: int,
    blocking_pid: int,
    timeout: float = 5.0,
    interval: float = 0.05,
) -> LockWait:
    """Poll until one specific blocking pair appears, or raise ``TimeoutError``.

    Polling instead of sleeping for a fixed duration keeps the happy path fast
    while still failing loudly when the expected wait never materialises.
    """

    deadline = time.monotonic() + timeout
    last_seen: tuple[LockWait, ...] = ()
    while time.monotonic() < deadline:
        last_seen = blocking_pairs(db)
        for pair in last_seen:
            if pair.blocked_pid == blocked_pid and pair.blocking_pid == blocking_pid:
                return pair
        time.sleep(interval)

    observed = ", ".join(
        f"{pair.blocked_pid}<-{pair.blocking_pid}" for pair in last_seen
    )
    raise TimeoutError(
        f"no lock wait {blocked_pid}<-{blocking_pid} within {timeout}s "
        f"(observed: {observed or 'none'})"
    )


def deadlock_count(db: DatabaseClient) -> int:
    """Return how many deadlocks this database has resolved since it started."""

    row = db.fetch_one(
        """
        SELECT deadlocks
        FROM pg_stat_database
        WHERE datname = current_database()
        """
    )
    if row is None:
        raise RuntimeError("pg_stat_database returned no row for the current database")
    return int(row["deadlocks"])


def active_waits(db: DatabaseClient) -> int:
    """Return how many sessions currently wait on a lock."""

    row = db.fetch_one(
        """
        SELECT COUNT(*) AS waiting
        FROM pg_locks
        WHERE NOT granted
        """
    )
    if row is None:
        raise RuntimeError("pg_locks returned no row")
    return int(row["waiting"])
