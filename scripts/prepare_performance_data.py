"""Provision the Week 26 isolated performance dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa_core.db import DatabaseClient
from qa_core.performance import (
    PerformanceDataPool,
    load_env_file,
    setting_from_sources,
)


def main() -> int:
    """Create one deterministic dataset and print only non-secret paths."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workspace-slug")
    parser.add_argument("--item-count", type=int, default=100)
    parser.add_argument("--account-count", type=int, default=16)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=root / ".env.performance.example",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=root / "artifacts" / "performance" / "week26",
    )
    args = parser.parse_args()

    env_file = load_env_file(args.env_file)
    dsn = setting_from_sources(
        "QA_POSTGRES_DSN",
        explicit=None,
        env_file=env_file,
    )
    redis_url = setting_from_sources(
        "QA_REDIS_URL",
        explicit=None,
        env_file=env_file,
    )
    password = setting_from_sources(
        "QA_AUTH_TEST_PASSWORD",
        explicit=None,
        env_file=env_file,
        default="local-test-password",
    )

    with DatabaseClient(
        dsn,
        application_name="week26-performance-data-pool",
    ) as db:
        pool = PerformanceDataPool(db, redis_url=redis_url)
        dataset = pool.provision(
            run_id=args.run_id,
            workspace_slug=args.workspace_slug,
            password=password,
            item_count=args.item_count,
            account_count=args.account_count,
            output_root=args.output_root,
        )
        counts = pool.counts(workspace_slug=dataset.manifest.workspace_slug)

    print(
        json.dumps(
            {
                "workspace_slug": dataset.manifest.workspace_slug,
                "metadata": str(dataset.metadata_path),
                "runtime_data": str(dataset.runtime_data_path),
                "counts": counts,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
