"""Check the local Docker Compose SUT and its external dependencies."""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass

import httpx
import redis

try:
    import psycopg
    from psycopg.rows import dict_row
except (ImportError, OSError) as exc:
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    PSYCOPG_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PSYCOPG_IMPORT_ERROR = ""

DEFAULT_API_BASE_URL = "http://127.0.0.1:18000"
DEFAULT_POSTGRES_DSN = "postgresql://qa:qa@127.0.0.1:15432/qa"
DEFAULT_REDIS_URL = "redis://127.0.0.1:26379/0"
DEFAULT_NAMESPACE_PREFIX = "qa-ns-"

# Canonical seed identity from apps/compose/postgres/init/002_seed.sql. Test
# namespaces are counted separately so a leaked workspace is reported as a
# leftover instead of looking like a broken seed.
SEED_WORKSPACE_SLUGS = ("atlas", "orbit")
SEED_USER_EMAILS = (
    "owner@atlas.example",
    "viewer@atlas.example",
    "admin@orbit.example",
)
SEED_ITEM_SKUS = ("LAB-001", "LAB-002", "LAB-003", "ORB-001")


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
                openapi = client.get("/openapi.json")
                catalog = client.get("/api/v1/workspaces/atlas/catalog")
                last_detail = (
                    f"live={live.status_code}, ready={ready.status_code}, "
                    f"openapi={openapi.status_code}, "
                    f"catalog={catalog.status_code}"
                )

                if (
                    live.status_code == 200
                    and ready.status_code == 200
                    and openapi.status_code == 200
                    and catalog.status_code == 200
                ):
                    openapi_payload = openapi.json()
                    catalog_payload = catalog.json()
                    skus = {item["sku"] for item in catalog_payload.get("items", [])}
                    paths = openapi_payload.get("paths", {})
                    if (
                        {"LAB-001", "LAB-002"}.issubset(skus)
                        and "/oauth/token" in paths
                        and "/api/v1/workspaces/{slug}/catalog" in paths
                        and "/api/v1/workspaces/{slug}/catalog/items" in paths
                    ):
                        return [
                            CheckResult("API live", True, "HTTP 200"),
                            CheckResult(
                                "API ready",
                                True,
                                json.dumps(ready.json(), sort_keys=True),
                            ),
                            CheckResult(
                                "OpenAPI contract",
                                True,
                                f"openapi={openapi_payload.get('openapi')}, "
                                f"paths={len(paths)}",
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


def check_postgres(postgres_dsn: str) -> list[CheckResult]:
    """Verify the seed identity and report any leaked test namespace."""

    if psycopg is None:
        return [
            CheckResult(
                "PostgreSQL",
                False,
                (
                    "psycopg import failed: "
                    f"{PSYCOPG_IMPORT_ERROR}. Check Smart App Control or use "
                    "the container-side psql verification."
                ),
            )
        ]

    try:
        with psycopg.connect(postgres_dsn, connect_timeout=3) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT current_database() AS database")
                database = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM workspaces
                         WHERE slug = ANY(%s)) AS workspaces,
                        (SELECT COUNT(*) FROM users u
                         JOIN workspaces w ON w.id = u.workspace_id
                         WHERE u.email = ANY(%s)) AS users,
                        (SELECT COUNT(*) FROM catalog_items i
                         JOIN workspaces w ON w.id = i.workspace_id
                         WHERE i.sku = ANY(%s)) AS items
                    """,
                    (
                        list(SEED_WORKSPACE_SLUGS),
                        list(SEED_USER_EMAILS),
                        list(SEED_ITEM_SKUS),
                    ),
                )
                counts = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS namespaces,
                        COALESCE(SUM(item_count), 0) AS items
                    FROM (
                        SELECT
                            w.id,
                            (SELECT COUNT(*) FROM catalog_items i
                             WHERE i.workspace_id = w.id) AS item_count
                        FROM workspaces w
                        WHERE starts_with(w.slug, %s)
                    ) AS leftovers
                    """,
                    (DEFAULT_NAMESPACE_PREFIX,),
                )
                leftovers = cursor.fetchone()
    except Exception as exc:  # noqa: BLE001
        return [CheckResult("PostgreSQL", False, f"{type(exc).__name__}: {exc}")]

    expected = {"workspaces": 2, "users": 3, "items": 4}
    passed = counts == expected
    detail = (
        f"database={database['database'] if database else None}, "
        f"counts={counts}, expected={expected}"
    )
    leftover_count = int(leftovers["namespaces"]) if leftovers else -1
    return [
        CheckResult("PostgreSQL seed", passed, detail),
        CheckResult(
            "Namespace leftovers",
            leftover_count == 0,
            f"test_namespaces={leftover_count}, prefix={DEFAULT_NAMESPACE_PREFIX!r}",
        ),
    ]


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
    checks.extend(check_postgres(args.postgres_dsn))
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
