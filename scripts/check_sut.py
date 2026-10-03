"""Check the local Docker Compose SUT and its external dependencies."""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass

import httpx
import psycopg
import redis
from psycopg.rows import dict_row

DEFAULT_API_BASE_URL = "http://127.0.0.1:18000"
DEFAULT_POSTGRES_DSN = "postgresql://qa:qa@127.0.0.1:15432/qa"
DEFAULT_REDIS_URL = "redis://127.0.0.1:16379/0"


@dataclass(frozen=True)
class CheckResult:
    """One SUT readiness result."""

    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("QA_API_BASE_URL", DEFAULT_API_BASE_URL),
        help="Host-side API base URL.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.getenv("QA_POSTGRES_DSN", DEFAULT_POSTGRES_DSN),
        help="Host-side PostgreSQL DSN.",
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("QA_REDIS_URL", DEFAULT_REDIS_URL),
        help="Host-side Redis URL.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=60,
        help="Maximum time to wait for API and dependency readiness.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=3.0,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser.parse_args()


def wait_for_http_checks(
    api_base_url: str,
    wait_seconds: int,
    request_timeout: float,
) -> list[CheckResult]:
    """Wait for live, ready, and seeded catalog endpoints."""

    deadline = time.monotonic() + max(wait_seconds, 1)
    api_base_url = api_base_url.rstrip("/")
    last_detail = "API has not been checked"

    with httpx.Client(base_url=api_base_url, timeout=request_timeout) as client:
        while time.monotonic() < deadline:
            try:
                live = client.get("/health/live")
                ready = client.get("/health/ready")
                catalog = client.get("/api/v1/workspaces/atlas/catalog")
                last_detail = (
                    f"live={live.status_code}, ready={ready.status_code}, "
                    f"catalog={catalog.status_code}"
                )

                if (
                    live.status_code == 200
                    and ready.status_code == 200
                    and catalog.status_code == 200
                ):
                    catalog_payload = catalog.json()
                    skus = {item["sku"] for item in catalog_payload.get("items", [])}
                    if {"LAB-001", "LAB-002"}.issubset(skus):
                        return [
                            CheckResult("API live", True, "HTTP 200"),
                            CheckResult(
                                "API ready",
                                True,
                                json.dumps(ready.json(), sort_keys=True),
                            ),
                            CheckResult(
                                "Seeded catalog",
                                True,
                                f"workspace=atlas, skus={sorted(skus)}",
                            ),
                        ]
            except (httpx.HTTPError, ValueError) as exc:
                last_detail = f"{type(exc).__name__}: {exc}"

            time.sleep(2)

    return [
        CheckResult("API live/ready/catalog", False, last_detail),
    ]


def check_postgres(postgres_dsn: str) -> CheckResult:
    """Verify the test schema and expected seed rows through a read-only query."""

    try:
        with psycopg.connect(postgres_dsn, connect_timeout=3) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT current_database() AS database")
                database = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM workspaces) AS workspaces,
                        (SELECT COUNT(*) FROM users) AS users,
                        (SELECT COUNT(*) FROM catalog_items) AS items
                    """
                )
                counts = cursor.fetchone()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("PostgreSQL", False, f"{type(exc).__name__}: {exc}")

    expected = {"workspaces": 2, "users": 3, "items": 4}
    passed = counts == expected
    detail = (
        f"database={database['database'] if database else None}, "
        f"counts={counts}, expected={expected}"
    )
    return CheckResult("PostgreSQL", passed, detail)


def check_redis(redis_url: str) -> CheckResult:
    """Verify Redis connectivity and key-space readability."""

    client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    try:
        pong = client.ping()
        database_size = client.dbsize()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Redis", False, f"{type(exc).__name__}: {exc}")
    finally:
        client.close()

    return CheckResult(
        "Redis",
        bool(pong),
        f"ping={bool(pong)}, dbsize={database_size}",
    )


def main() -> int:
    """Run all SUT checks and return a process exit code."""

    args = parse_args()
    checks = wait_for_http_checks(
        api_base_url=args.api_base_url,
        wait_seconds=args.wait_seconds,
        request_timeout=args.request_timeout,
    )
    checks.append(check_postgres(args.postgres_dsn))
    checks.append(check_redis(args.redis_url))
    passed = all(check.passed for check in checks)

    if args.json:
        print(
            json.dumps(
                {
                    "passed": passed,
                    "api_base_url": args.api_base_url.rstrip("/"),
                    "checks": [asdict(check) for check in checks],
                },
                indent=2,
            )
        )
    else:
        for check in checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"{status} {check.name}: {check.detail}")
        print(f"SUT ready: {passed}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
