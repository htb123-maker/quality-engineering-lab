"""Clean one Week 26 isolated performance dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa_core.db import DatabaseClient
from qa_core.performance import (
    PerformanceDataPool,
    load_env_file,
    normalize_run_id,
    performance_workspace_slug,
    setting_from_sources,
)


def main() -> int:
    """Purge database rows and cache keys, then print post-cleanup counts."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workspace-slug")
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
    workspace_slug = args.workspace_slug or performance_workspace_slug(args.run_id)

    with DatabaseClient(
        dsn,
        application_name="week26-performance-data-cleanup",
    ) as db:
        pool = PerformanceDataPool(db, redis_url=redis_url)
        counts = pool.cleanup(workspace_slug=workspace_slug)

    runtime_data_path = (
        args.output_root.resolve() / "data" / normalize_run_id(args.run_id) / "runtime.json"
    )
    runtime_removed = False
    if runtime_data_path.is_file():
        runtime_data_path.unlink()
        runtime_removed = True
    print(
        json.dumps(
            {
                "workspace_slug": workspace_slug,
                "post_cleanup_counts": counts,
                "runtime_data_removed": runtime_removed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
