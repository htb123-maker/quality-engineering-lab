"""Run one Week 26 performance profile with repeated measured runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qa_core.cache.catalog import purge_catalog_cache
from qa_core.performance import (
    DockerResourceSampler,
    ObservedPerformance,
    evaluate_thresholds,
    load_performance_profile,
    load_runtime_data,
    profile_sha256,
    summarize_observations,
)


def main() -> int:
    """Execute warmup and measured runs, then write a median summary."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--data-file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=int, default=15)
    parser.add_argument("--measured-runs", type=int, default=3)
    parser.add_argument("--resource-interval", type=float, default=2.0)
    parser.add_argument("--compose-project", default="quality-engineering-lab-performance")
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=root / "apps" / "compose" / "compose.yaml",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=root / ".env.performance.example",
    )
    args = parser.parse_args()

    profile_path = args.profile.resolve()
    profile = load_performance_profile(profile_path)
    output_dir = args.output_dir.resolve()
    label_dir = output_dir / args.label
    label_dir.mkdir(parents=True, exist_ok=True)
    if args.measured_runs < 1:
        raise ValueError("measured-runs must be at least one")

    data_file: Path | None = None
    runtime = None
    if profile.authentication == "password":
        if args.data_file is None:
            raise ValueError("--data-file is required for authenticated profiles")
        data_file = args.data_file.resolve()
        runtime = load_runtime_data(data_file)
        if runtime.workspace_slug != profile.workspace:
            raise ValueError(
                "profile workspace does not match authenticated runtime data: "
                f"{profile.workspace!r} != {runtime.workspace_slug!r}"
            )
        purge_catalog_cache(runtime.redis_url, runtime.workspace_slug)

    metadata = {
        "profile_path": str(profile_path),
        "profile_sha256": profile_sha256(profile_path),
        "git_commit": _command_output(["git", "rev-parse", "HEAD"], root),
        "worktree_dirty": bool(_command_output(["git", "status", "--porcelain"], root)),
        "python_version": sys.version,
        "locust_version": _command_output(
            [sys.executable, "-m", "locust", "--version"],
            root,
        ),
        "data_file_sha256": (
            hashlib.sha256(data_file.read_bytes()).hexdigest() if data_file is not None else None
        ),
    }

    if args.warmup_seconds > 0:
        _run_locust(
            root=root,
            profile_path=profile_path,
            data_file=data_file,
            run_dir=label_dir / "warmup",
            run_id=f"{profile.name}-warmup",
            warmup_seconds=args.warmup_seconds,
            skip_slo=True,
            metadata=metadata,
            compose_project=args.compose_project,
            compose_file=args.compose_file,
            env_file=args.env_file,
            resource_interval=args.resource_interval,
            expected_duration=args.warmup_seconds,
        )

    measured_results: list[dict[str, Any]] = []
    for index in range(1, args.measured_runs + 1):
        run_dir = label_dir / f"run-{index:02d}"
        result = _run_locust(
            root=root,
            profile_path=profile_path,
            data_file=data_file,
            run_dir=run_dir,
            run_id=f"{profile.name}-run-{index:02d}",
            warmup_seconds=0,
            skip_slo=False,
            metadata=metadata,
            compose_project=args.compose_project,
            compose_file=args.compose_file,
            env_file=args.env_file,
            resource_interval=args.resource_interval,
            expected_duration=sum(stage.duration_seconds for stage in profile.stages),
        )
        measured_results.append(result)

    observations = [
        ObservedPerformance.model_validate(result["observed"]) for result in measured_results
    ]
    summary_observed = summarize_observations(observations)
    passed, threshold_results = evaluate_thresholds(
        profile.thresholds,
        summary_observed,
    )
    summary = {
        "schema_version": 1,
        "profile_name": profile.name,
        "profile_path": str(profile_path),
        "profile_sha256": metadata["profile_sha256"],
        "measured_runs": args.measured_runs,
        "run_ids": [result["run_id"] for result in measured_results],
        "observed": summary_observed.model_dump(mode="json"),
        "individual_observations": [
            observation.model_dump(mode="json") for observation in observations
        ],
        "thresholds": [result.model_dump(mode="json") for result in threshold_results],
        "slo_passed": passed,
        "git_commit": metadata["git_commit"],
        "worktree_dirty": metadata["worktree_dirty"],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    summary_path = label_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if passed else 1


def _run_locust(
    *,
    root: Path,
    profile_path: Path,
    data_file: Path | None,
    run_dir: Path,
    run_id: str,
    warmup_seconds: int,
    skip_slo: bool,
    metadata: dict[str, Any],
    compose_project: str,
    compose_file: Path,
    env_file: Path,
    resource_interval: float,
    expected_duration: int,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "locust.log"
    resources_path = run_dir / "resources.csv"
    csv_prefix = run_dir / "locust"
    command = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(root / "performance" / "locustfiles" / "api_journeys.py"),
        "--headless",
        "--only-summary",
        "--csv",
        str(csv_prefix),
        "--csv-full-history",
        "--html",
        str(run_dir / "report.html"),
        "--exit-code-on-error",
        "1",
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = f"{root / 'packages'}{os.pathsep}{root}" + (
        f"{os.pathsep}{environment['PYTHONPATH']}" if environment.get("PYTHONPATH") else ""
    )
    environment["QA_PERF_PROFILE"] = str(profile_path)
    environment["QA_PERF_RUN_DIR"] = str(run_dir)
    environment["QA_PERF_RUN_ID"] = run_id
    environment["QA_PERF_WARMUP_SECONDS"] = str(warmup_seconds)
    environment["QA_PERF_SKIP_SLO"] = "1" if skip_slo else "0"
    if data_file is not None:
        environment["QA_PERF_DATA_FILE"] = str(data_file)

    started_at = datetime.now(UTC).isoformat()
    with DockerResourceSampler(
        root=root,
        project=compose_project,
        env_file=env_file,
        compose_file=compose_file,
        run_id=run_id,
        profile=metadata["profile_path"],
        output_path=resources_path,
        interval_seconds=resource_interval,
    ):
        with log_path.open("w", encoding="utf-8") as log_file:
            completed = subprocess.run(
                command,
                cwd=root,
                env=environment,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=expected_duration + 180,
            )
    if completed.returncode != 0:
        tail = "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-40:])
        raise RuntimeError(f"Locust run failed with exit code {completed.returncode}:\n{tail}")
    result_path = run_dir / "result.json"
    if not result_path.is_file():
        raise RuntimeError(f"Locust did not write {result_path}")
    result: dict[str, Any] = json.loads(result_path.read_text(encoding="utf-8"))
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "warmup_seconds": warmup_seconds,
        "skipped_slo": skip_slo,
        "result_path": str(result_path),
        "resources_path": str(resources_path),
        "locust_log_path": str(log_path),
        **metadata,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _command_output(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )
    return (completed.stdout or completed.stderr).strip()


if __name__ == "__main__":
    raise SystemExit(main())
