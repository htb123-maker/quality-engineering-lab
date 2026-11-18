"""Verify two performance runs coexist and cleanup is selective."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qa_core.db import DatabaseClient
from qa_core.performance import (
    PerformanceDataPool,
    load_env_file,
    performance_workspace_slug,
    setting_from_sources,
)


def main() -> int:
    """Provision two runs, clean one, and preserve the other."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-prefix", default="week26-isolation")
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
    run_a = f"{args.run_prefix}-a"
    run_b = f"{args.run_prefix}-b"
    slug_a = performance_workspace_slug(run_a)
    slug_b = performance_workspace_slug(run_b)
    output_root = args.output_root.resolve()
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "run_a": {"run_id": run_a, "workspace_slug": slug_a},
        "run_b": {"run_id": run_b, "workspace_slug": slug_b},
    }

    with DatabaseClient(
        dsn,
        application_name="week26-performance-isolation-verification",
    ) as db:
        pool = PerformanceDataPool(db, redis_url=redis_url)
        try:
            pool.cleanup(workspace_slug=slug_a)
            pool.cleanup(workspace_slug=slug_b)
            dataset_a = pool.provision(
                run_id=run_a,
                workspace_slug=slug_a,
                password=password,
                item_count=20,
                account_count=4,
                output_root=output_root,
            )
            dataset_b = pool.provision(
                run_id=run_b,
                workspace_slug=slug_b,
                password=password,
                item_count=30,
                account_count=5,
                output_root=output_root,
            )
            counts_a_initial = pool.counts(workspace_slug=slug_a)
            counts_b_initial = pool.counts(workspace_slug=slug_b)
            _expect(
                counts_a_initial,
                {"workspaces": 1, "users": 4, "items": 20},
                "run A initial counts",
            )
            _expect(
                counts_b_initial,
                {"workspaces": 1, "users": 5, "items": 30},
                "run B initial counts",
            )

            cleanup_a = pool.cleanup(workspace_slug=slug_a)
            counts_a_after = pool.counts(workspace_slug=slug_a)
            counts_b_after = pool.counts(workspace_slug=slug_b)
            _expect(
                cleanup_a,
                {"workspaces": 0, "users": 0, "items": 0},
                "run A cleanup counts",
            )
            _expect(
                counts_a_after,
                {"workspaces": 0, "users": 0, "items": 0},
                "run A post-cleanup counts",
            )
            _expect(
                counts_b_after,
                {"workspaces": 1, "users": 5, "items": 30},
                "run B preserved counts",
            )

            cleanup_b = pool.cleanup(workspace_slug=slug_b)
            counts_b_final = pool.counts(workspace_slug=slug_b)
            _expect(
                cleanup_b,
                {"workspaces": 0, "users": 0, "items": 0},
                "run B cleanup counts",
            )
            _expect(
                counts_b_final,
                {"workspaces": 0, "users": 0, "items": 0},
                "run B post-cleanup counts",
            )

            evidence.update(
                {
                    "run_a_initial": counts_a_initial,
                    "run_b_initial": counts_b_initial,
                    "run_a_after_cleanup": counts_a_after,
                    "run_b_after_run_a_cleanup": counts_b_after,
                    "run_b_final": counts_b_final,
                    "selective_cleanup_passed": True,
                }
            )
            dataset_a.runtime_data_path.unlink(missing_ok=True)
            dataset_b.runtime_data_path.unlink(missing_ok=True)
            evidence["runtime_data_removed"] = True
        finally:
            pool.cleanup(workspace_slug=slug_a)
            pool.cleanup(workspace_slug=slug_b)
            for run_id in (run_a, run_b):
                runtime_path = output_root / "data" / run_id / "runtime.json"
                runtime_path.unlink(missing_ok=True)

    evidence_path = output_root / "isolation-verification.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


def _expect(actual: dict[str, int], expected: dict[str, int], label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


if __name__ == "__main__":
    raise SystemExit(main())
