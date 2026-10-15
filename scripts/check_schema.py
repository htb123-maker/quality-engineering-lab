"""Verify the local Compose PostgreSQL schema against its expected contract.

The check is read-only: it never creates, alters, or drops anything. It exists
because ``apps/compose/postgres/init/001_schema.sql`` only runs on a fresh
volume, so an already-initialised database can silently drift from the schema
every database test assumes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(ROOT / "packages"))

from qa_core.db import (  # noqa: E402
    EXPECTED_TABLES,
    EXPECTED_VIEWS,
    DatabaseClient,
    SchemaViolation,
    check_schema_contract,
    list_tables,
    list_views,
)

DEFAULT_POSTGRES_DSN = "postgresql://qa:qa@127.0.0.1:15432/qa"


@dataclass(frozen=True)
class SchemaCheck:
    """One reported schema check."""

    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--postgres-dsn",
        default=os.getenv("QA_POSTGRES_DSN", DEFAULT_POSTGRES_DSN),
        help="Host-side PostgreSQL DSN.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser.parse_args()


def run_checks(dsn: str) -> list[SchemaCheck]:
    """Read the live schema and report contract violations."""

    try:
        with DatabaseClient(dsn, connect_timeout=5) as db:
            tables = list_tables(db)
            views = list_views(db)
            violations = check_schema_contract(db)
    except Exception as exc:  # noqa: BLE001
        return [
            SchemaCheck(
                "PostgreSQL schema",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        ]

    return [
        SchemaCheck(
            "Schema tables",
            True,
            f"tables={len(tables)}, expected={len(EXPECTED_TABLES)}, "
            f"names={','.join(tables)}",
        ),
        SchemaCheck(
            "Schema views",
            True,
            f"views={len(views)}, expected={len(EXPECTED_VIEWS)}, "
            f"names={','.join(views)}",
        ),
        SchemaCheck(
            "Schema contract",
            not violations,
            (
                f"tables={len(EXPECTED_TABLES)}, views={len(EXPECTED_VIEWS)}, "
                f"violations={len(violations)}"
            ),
        ),
        *_violation_checks(violations),
    ]


def _violation_checks(violations: tuple[SchemaViolation, ...]) -> list[SchemaCheck]:
    return [
        SchemaCheck(f"Drift {violation.target}", False, violation.message)
        for violation in violations
    ]


def main() -> int:
    """Run the schema check and return a process exit code."""

    args = parse_args()
    checks = run_checks(args.postgres_dsn)
    passed = all(check.passed for check in checks)

    if args.json:
        print(
            json.dumps(
                {
                    "passed": passed,
                    "postgres_dsn": args.postgres_dsn,
                    "checks": [asdict(check) for check in checks],
                },
                indent=2,
            )
        )
    else:
        for check in checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"{status} {check.name}: {check.detail}")
        print(f"Schema check: {'PASS' if passed else 'FAIL'}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
