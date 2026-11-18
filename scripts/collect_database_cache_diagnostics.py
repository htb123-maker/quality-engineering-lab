"""Collect Week 29 PostgreSQL, WAL, connection-pool, and Redis evidence."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
import redis
from psycopg.rows import dict_row
from qa_core.db import DatabaseClient, execution_time_ms, explain_json, plan_node_types
from qa_core.performance import load_env_file


def _fetch_one(
    connection: psycopg.Connection[dict[str, Any]],
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def _fetch_all(
    connection: psycopg.Connection[dict[str, Any]],
    sql: str,
) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()


def _redis_info(client: redis.Redis) -> dict[str, Any]:
    raw = client.info()
    hits = int(raw.get("keyspace_hits", 0))
    misses = int(raw.get("keyspace_misses", 0))
    total = hits + misses
    return {
        "used_memory_bytes": int(raw.get("used_memory", 0)),
        "used_memory_peak_bytes": int(raw.get("used_memory_peak", 0)),
        "maxmemory_bytes": int(raw.get("maxmemory", 0)),
        "maxmemory_policy": raw.get("maxmemory_policy"),
        "connected_clients": int(raw.get("connected_clients", 0)),
        "evicted_keys": int(raw.get("evicted_keys", 0)),
        "expired_keys": int(raw.get("expired_keys", 0)),
        "keyspace_hits": hits,
        "keyspace_misses": misses,
        "hit_ratio": hits / total if total else None,
        "db_size": int(client.dbsize()),
        "keyspace": raw.get("db0", {}),
    }


def collect(args: argparse.Namespace) -> dict[str, Any]:
    values = load_env_file(args.env_file.resolve())
    dsn = values["QA_POSTGRES_DSN"]
    redis_url = values["QA_REDIS_URL"]
    api_url = values["QA_API_BASE_URL"]

    with psycopg.connect(
        dsn,
        autocommit=True,
        row_factory=dict_row,
        application_name="week29-diagnostics",
    ) as connection:
        version = _fetch_one(connection, "SELECT version() AS value")
        max_connections = _fetch_one(connection, "SHOW max_connections")
        connection_states = _fetch_all(
            connection,
            """
            SELECT COALESCE(state, 'unknown') AS state, COUNT(*) AS sessions
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY state
            ORDER BY state
            """,
        )
        database_stats = _fetch_one(
            connection,
            """
            SELECT datname, numbackends, xact_commit, xact_rollback,
                   blks_read, blks_hit, temp_bytes, deadlocks,
                   checksum_failures, stats_reset
            FROM pg_stat_database
            WHERE datname = current_database()
            """,
        )
        wal_stats = _fetch_one(connection, "SELECT * FROM pg_stat_wal")
        try:
            statements = _fetch_all(
                connection,
                """
                SELECT queryid, calls, mean_exec_time, total_exec_time, rows,
                       shared_blks_hit, shared_blks_read
                FROM pg_stat_statements
                ORDER BY mean_exec_time DESC
                LIMIT 10
                """,
            )
            statements_status = "AVAILABLE"
        except psycopg.errors.UndefinedTable:
            statements = []
            statements_status = "NOT_INSTALLED"

    with DatabaseClient(dsn, application_name="week29-plan") as database:
        workspace = database.fetch_one(
            "SELECT id FROM workspaces WHERE slug = 'atlas'"
        )
        if workspace is None:
            raise RuntimeError("seed workspace 'atlas' was not found")
        plan = explain_json(
            database,
            """
            SELECT id, sku
            FROM catalog_items
            WHERE workspace_id = %s AND status = 'active'
            ORDER BY sku
            """,
            (int(workspace["id"]),),
        )

    redis_client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
    )
    redis_evidence = _redis_info(redis_client)
    redis_client.close()

    with httpx.Client(base_url=api_url.rstrip("/"), timeout=10.0) as client:
        metrics = client.get("/metrics")
        metrics.raise_for_status()
        pool_metrics = {
            line.split()[0]: float(line.split()[1])
            for line in metrics.text.splitlines()
            if line.startswith("qa_sut_postgres_connection_budget_")
        }

    checks = {
        "postgres_reachable": version is not None,
        "wal_stats_available": wal_stats is not None,
        "connection_budget_metrics_available": bool(pool_metrics),
        "redis_reachable": redis_evidence["db_size"] >= 0,
        "redis_hit_ratio_available": redis_evidence["hit_ratio"] is not None,
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "postgres": {
            "version": version["value"] if version else None,
            "max_connections": int(max_connections["max_connections"])
            if max_connections
            else None,
            "connection_states": connection_states,
            "database_stats": database_stats,
            "wal_stats": wal_stats,
            "query_plan": plan,
            "query_plan_node_types": plan_node_types(plan),
            "query_execution_ms": execution_time_ms(plan),
            "pg_stat_statements_status": statements_status,
            "top_statements": statements,
        },
        "connection_pool_metrics": pool_metrics,
        "redis": redis_evidence,
        "checks": checks,
        "passed": all(checks.values()),
    }


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=root / ".env.performance.example",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root
        / "artifacts"
        / "performance"
        / "week29"
        / "week29-soak"
        / "database-cache-diagnostics.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = collect(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"Evidence: {args.output.resolve()}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
