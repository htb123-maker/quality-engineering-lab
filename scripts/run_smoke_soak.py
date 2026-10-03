"""Run the smoke matrix repeatedly and record session, port, and process leaks.

The matrix entry point is reused as a subprocess so this script only adds the
repetition and the baseline/final environment comparison.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from qa_core.reporting import (  # noqa: E402
    EnvironmentSnapshot,
    compare_snapshots,
    parse_pytest_summary,
)

MATRIX_SCRIPT = Path(__file__).resolve().parent / "run_smoke_matrix.py"

DEFAULT_SESSIONS_URL = "http://127.0.0.1:4723/sessions"
DEFAULT_WATCH_PORTS = (4723, 5554, 5555, 18000, 15432, 16379)
DEFAULT_PROCESS_PATTERNS = ("appium", "emulator", "qemu-system", "adb")

_CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of smoke matrix repetitions.",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=("api", "android", "ios"),
        default=("api", "android"),
        help="Smoke suites forwarded to the matrix runner.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("artifacts/smoke-soak.json"),
        help="Path for the machine-readable soak summary.",
    )
    parser.add_argument(
        "--allure-results",
        type=Path,
        default=Path("artifacts/allure-results"),
        help="Shared Allure results directory for every iteration.",
    )
    parser.add_argument(
        "--sessions-url",
        default=DEFAULT_SESSIONS_URL,
        help="Appium session listing endpoint.",
    )
    parser.add_argument(
        "--watch-ports",
        type=int,
        nargs="+",
        default=list(DEFAULT_WATCH_PORTS),
        help="Local ports compared between the baseline and final snapshot.",
    )
    parser.add_argument(
        "--process-patterns",
        nargs="+",
        default=list(DEFAULT_PROCESS_PATTERNS),
        help="Command-line substrings counted in both snapshots.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=900.0,
        help="Per-iteration timeout for the smoke matrix.",
    )
    return parser.parse_args()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _port_is_open(port: int, timeout: float) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _appium_sessions(sessions_url: str, timeout: float) -> tuple[str, ...]:
    try:
        response = httpx.get(sessions_url, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError:
        return ()

    payload = response.json()
    value = payload.get("value", payload)
    if not isinstance(value, list):
        return ()

    sessions: list[str] = []
    for entry in value:
        if isinstance(entry, dict) and entry.get("id"):
            sessions.append(str(entry["id"]))
    return tuple(sessions)


def _process_command_lines() -> tuple[str, ...]:
    if sys.platform == "win32":
        command = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-CimInstance Win32_Process | Select-Object -ExpandProperty CommandLine",
        ]
    else:
        command = ["ps", "-eo", "args="]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=_CHILD_ENV,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    stdout = completed.stdout or ""
    return tuple(line for line in stdout.splitlines() if line.strip())


def _process_counts(patterns: tuple[str, ...]) -> dict[str, int]:
    lines = [line.lower() for line in _process_command_lines()]
    return {pattern: sum(pattern in line for line in lines) for pattern in patterns}


def _snapshot(
    sessions_url: str,
    watch_ports: tuple[int, ...],
    process_patterns: tuple[str, ...],
    timeout: float,
) -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        captured_at=_now(),
        appium_sessions=_appium_sessions(sessions_url, timeout),
        open_ports=tuple(port for port in watch_ports if _port_is_open(port, timeout)),
        processes=_process_counts(process_patterns),
    )


def _run_iteration(
    index: int,
    args: argparse.Namespace,
    soak_dir: Path,
    allure_results: Path,
) -> dict[str, Any]:
    matrix_json = soak_dir / f"matrix-{index:02d}.json"
    command = [
        sys.executable,
        str(MATRIX_SCRIPT),
        "--targets",
        *args.targets,
        "--json-output",
        str(matrix_json),
        "--allure-results",
        str(allure_results),
    ]

    started_at = _now()
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=_CHILD_ENV,
            timeout=args.timeout_seconds,
        )
        exit_code = completed.returncode
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        exit_code = 124
        output = f"Smoke matrix exceeded {args.timeout_seconds:.0f}s."
    finished_at = _now()

    targets: list[dict[str, Any]] = []
    if matrix_json.exists():
        matrix = json.loads(matrix_json.read_text(encoding="utf-8"))
        for result in matrix.get("targets", []):
            targets.append(
                {
                    "name": result.get("name"),
                    "exit_code": result.get("exit_code"),
                    "outcome": parse_pytest_summary(str(result.get("output_tail", ""))),
                    "duration_seconds": result.get("duration_seconds"),
                }
            )

    return {
        "index": index,
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": exit_code,
        "passed": exit_code == 0,
        "targets": targets,
        "output_tail": output[-2000:],
    }


def main() -> int:
    args = _parse_args()
    if args.iterations < 1:
        raise SystemExit("--iterations must be at least 1.")

    json_output = (PROJECT_ROOT / args.json_output).resolve()
    allure_results = (PROJECT_ROOT / args.allure_results).resolve()
    soak_dir = json_output.parent / "soak"
    soak_dir.mkdir(parents=True, exist_ok=True)
    allure_results.mkdir(parents=True, exist_ok=True)

    watch_ports = tuple(args.watch_ports)
    process_patterns = tuple(args.process_patterns)
    snapshot_timeout = 3.0

    baseline = _snapshot(
        args.sessions_url, watch_ports, process_patterns, snapshot_timeout
    )
    print(f"[baseline] sessions={list(baseline.appium_sessions)}")
    print(f"[baseline] open_ports={list(baseline.open_ports)}")
    print(f"[baseline] processes={baseline.processes}")

    started_at = _now()
    iterations: list[dict[str, Any]] = []
    for index in range(1, args.iterations + 1):
        print(f"\n=== iteration {index}/{args.iterations} ===")
        record = _run_iteration(index, args, soak_dir, allure_results)
        snapshot = _snapshot(
            args.sessions_url, watch_ports, process_patterns, snapshot_timeout
        )
        verdict = compare_snapshots(baseline, snapshot)
        record["snapshot"] = snapshot.to_dict()
        record["leaked_since_baseline"] = verdict.leaked
        iterations.append(record)

        outcomes = ", ".join(
            f"{target['name']}:{target['outcome'] or target['exit_code']}"
            for target in record["targets"]
        )
        print(f"[iteration {index}] exit={record['exit_code']} {outcomes}")
        print(f"[iteration {index}] leaked_since_baseline={verdict.leaked}")
    finished_at = _now()

    final = _snapshot(args.sessions_url, watch_ports, process_patterns, snapshot_timeout)
    verdict = compare_snapshots(baseline, final)

    all_passed = bool(iterations) and all(
        bool(record["passed"]) for record in iterations
    )
    summary: dict[str, Any] = {
        "started_at": started_at,
        "finished_at": finished_at,
        "project_root": str(PROJECT_ROOT),
        "allure_results": str(allure_results),
        "iterations_requested": args.iterations,
        "iterations_completed": len(iterations),
        "targets": list(args.targets),
        "all_passed": all_passed,
        "baseline": baseline.to_dict(),
        "final": final.to_dict(),
        "verdict": verdict.to_dict(),
        "iterations": iterations,
        "passed": all_passed and not verdict.leaked,
    }
    json_output.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("\n=== soak verdict ===")
    print(f"iterations: {len(iterations)}/{args.iterations}")
    print(f"all iterations passed: {all_passed}")
    print(f"leaked: {verdict.leaked}")
    if verdict.leaked:
        print(f"new appium sessions: {list(verdict.new_appium_sessions)}")
        print(f"ports opened: {list(verdict.ports_opened)}")
        print(f"process growth: {verdict.process_growth}")
    if verdict.ports_closed:
        print(f"ports closed (service regression): {list(verdict.ports_closed)}")
    print(f"Soak summary: {json_output}")

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
