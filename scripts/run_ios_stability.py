"""Run repeated iOS pytest executions and summarize first-seen outcomes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from qa_core.platforms.ios.stability import (
    read_junit_results,
    summarize_stability,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse repeat count, pytest targets, and report paths."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Pytest target; repeat the option to run multiple paths.",
    )
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path("artifacts/ios-week21/stability-runs"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/ios-week21/stability.json"),
    )
    parser.add_argument("--allure-dir", type=Path)
    parser.add_argument("--pass-threshold", type=float, default=0.98)
    parser.add_argument("--flaky-threshold", type=float, default=0.02)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute every run, parse JUnit, and write one aggregate report."""

    args = parse_args(argv)
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    if not 0.0 <= args.pass_threshold <= 1.0:
        raise SystemExit("--pass-threshold must be between 0 and 1")
    if not 0.0 <= args.flaky_threshold <= 1.0:
        raise SystemExit("--flaky-threshold must be between 0 and 1")

    targets = args.target or ["tests/ios"]
    run_dir = _project_path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    allure_root = _project_path(args.allure_dir) if args.allure_dir else None
    output = _project_path(args.output)

    run_results = []
    for run_index in range(1, args.runs + 1):
        junit_path = run_dir / f"run-{run_index}.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            *targets,
            "-q",
            f"--junitxml={junit_path}",
        ]
        if allure_root is not None:
            command.append(f"--alluredir={allure_root / f'run-{run_index}'}")
        print(f"[run {run_index}/{args.runs}] {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        if not junit_path.is_file():
            raise SystemExit(
                f"pytest run {run_index} did not produce {junit_path}"
            )
        run_results.append(
            read_junit_results(junit_path, run_index=run_index)
        )

    summary = summarize_stability(
        run_results,
        required_runs=args.runs,
        pass_threshold=args.pass_threshold,
        flaky_threshold=args.flaky_threshold,
    )
    payload = {
        **summary.to_payload(),
        "targets": targets,
        "junit_reports": [
            result.junit_path.relative_to(PROJECT_ROOT).as_posix()
            for result in run_results
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if summary.passed_gate else 1


def _project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


if __name__ == "__main__":
    raise SystemExit(main())
