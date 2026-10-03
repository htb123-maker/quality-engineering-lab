"""Run API, Android, and iOS smoke suites and write one machine-readable summary."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SmokeTarget:
    """One environment-specific smoke suite."""

    name: str
    path: str
    environment_note: str


TARGETS = {
    "api": SmokeTarget(
        name="api",
        path="tests/api",
        environment_note="Requires the local Compose SUT.",
    ),
    "android": SmokeTarget(
        name="android",
        path="tests/android",
        environment_note="Requires a booted AVD and a ready Appium server.",
    ),
    "ios": SmokeTarget(
        name="ios",
        path="tests/ios",
        environment_note="Requires macOS, Xcode, Simulator, and a ready Appium server.",
    ),
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=tuple(TARGETS),
        default=tuple(TARGETS),
        help="Smoke suites to run. Defaults to all targets.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("artifacts/smoke-matrix.json"),
        help="Path for the machine-readable summary.",
    )
    parser.add_argument(
        "--allure-results",
        type=Path,
        default=Path("artifacts/allure-results"),
        help="Shared Allure results directory.",
    )
    return parser.parse_args()


def _run_target(
    target: SmokeTarget,
    project_root: Path,
    allure_results: Path,
) -> dict[str, object]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        target.path,
        "-q",
        "-m",
        "smoke",
        "-p",
        "no:cacheprovider",
        f"--alluredir={allure_results}",
    ]
    started_at = datetime.now(UTC)
    completed = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=900,
    )
    duration_seconds = round(
        (datetime.now(UTC) - started_at).total_seconds(),
        3,
    )
    output = (completed.stdout + completed.stderr).strip()

    print(f"\n[{target.name}] {' '.join(command)}")
    print(output)

    return {
        "name": target.name,
        "path": target.path,
        "environment_note": target.environment_note,
        "command": command,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "duration_seconds": duration_seconds,
        "output_tail": output[-4000:],
    }


def main() -> int:
    args = _parse_args()
    project_root = Path(__file__).resolve().parents[1]
    allure_results = (project_root / args.allure_results).resolve()
    json_output = (project_root / args.json_output).resolve()
    allure_results.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(UTC)
    selected_targets = [TARGETS[name] for name in args.targets]
    results = [
        _run_target(target, project_root, allure_results) for target in selected_targets
    ]
    finished_at = datetime.now(UTC)
    summary = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "project_root": str(project_root),
        "allure_results": str(allure_results),
        "targets": results,
        "passed": all(bool(result["passed"]) for result in results),
    }
    json_output.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"\nSmoke matrix summary: {json_output}")

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
