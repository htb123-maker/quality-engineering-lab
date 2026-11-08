"""Run Locust master/worker roles for Week 26 topology acceptance."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from qa_core.performance import (
    DockerResourceSampler,
    load_performance_profile,
    profile_sha256,
)

Role = Literal["local", "master", "worker"]


def main() -> int:
    """Run a local master/worker pair or one cross-host role."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--data-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--role", choices=("local", "master", "worker"), default="local")
    parser.add_argument("--expected-workers", type=int, default=1)
    parser.add_argument("--master-host", default="127.0.0.1")
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
    if args.expected_workers < 1:
        raise ValueError("expected-workers must be at least one")

    profile_path = args.profile.resolve()
    profile = load_performance_profile(profile_path)
    data_file = args.data_file.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    environment = _environment(root, profile_path, data_file)

    if args.role == "worker":
        return _run_worker(
            root,
            environment,
            master_host=args.master_host,
            log_path=output_dir / f"worker-{os.getpid()}.log",
        )
    if args.role == "master":
        return _run_master_only(
            args=args,
            root=root,
            profile=profile,
            profile_path=profile_path,
            environment=environment,
            output_dir=output_dir,
            data_file=data_file,
        )
    return _run_local_pair(
        args=args,
        root=root,
        profile=profile,
        profile_path=profile_path,
        environment=environment,
        output_dir=output_dir,
        data_file=data_file,
    )


def _run_local_pair(
    *,
    args: argparse.Namespace,
    root: Path,
    profile: Any,
    profile_path: Path,
    environment: dict[str, str],
    output_dir: Path,
    data_file: Path,
) -> int:
    worker_log = (output_dir / "worker-01.log").open("w", encoding="utf-8")
    worker_command = _worker_command(root, master_host="127.0.0.1")
    worker_environment = environment.copy()
    worker_environment["QA_PERF_WORKER"] = "1"
    worker = subprocess.Popen(
        worker_command,
        cwd=root,
        env=worker_environment,
        stdout=worker_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(2)
    master_result = _run_master(
        root=root,
        profile=profile,
        profile_path=profile_path,
        environment=environment,
        output_dir=output_dir,
        run_id=args.run_id,
        expected_workers=args.expected_workers,
        data_file=data_file,
        compose_project=args.compose_project,
        compose_file=args.compose_file,
        env_file=args.env_file,
    )
    try:
        worker.wait(timeout=30)
    except subprocess.TimeoutExpired:
        worker.terminate()
        worker.wait(timeout=10)
    finally:
        worker_log.close()
    if worker.returncode != 0:
        raise RuntimeError(f"Locust worker failed; see {output_dir / 'worker-01.log'}")
    return master_result


def _run_master_only(
    *,
    args: argparse.Namespace,
    root: Path,
    profile: Any,
    profile_path: Path,
    environment: dict[str, str],
    output_dir: Path,
    data_file: Path,
) -> int:
    return _run_master(
        root=root,
        profile=profile,
        profile_path=profile_path,
        environment=environment,
        output_dir=output_dir,
        run_id=args.run_id,
        expected_workers=args.expected_workers,
        data_file=data_file,
        compose_project=args.compose_project,
        compose_file=args.compose_file,
        env_file=args.env_file,
    )


def _run_master(
    *,
    root: Path,
    profile: Any,
    profile_path: Path,
    environment: dict[str, str],
    output_dir: Path,
    run_id: str,
    expected_workers: int,
    data_file: Path,
    compose_project: str,
    compose_file: Path,
    env_file: Path,
) -> int:
    run_environment = environment.copy()
    run_environment["QA_PERF_RUN_DIR"] = str(output_dir)
    run_environment["QA_PERF_RUN_ID"] = run_id
    log_path = output_dir / "master.log"
    command = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(root / "performance" / "locustfiles" / "api_journeys.py"),
        "--master",
        "--headless",
        "--only-summary",
        "--expect-workers",
        str(expected_workers),
        "--csv",
        str(output_dir / "locust"),
        "--csv-full-history",
        "--html",
        str(output_dir / "report.html"),
        "--exit-code-on-error",
        "1",
    ]
    expected_duration = sum(stage.duration_seconds for stage in profile.stages)
    started_at = datetime.now(UTC).isoformat()
    with DockerResourceSampler(
        root=root,
        project=compose_project,
        env_file=env_file,
        compose_file=compose_file,
        run_id=run_id,
        profile=str(profile_path),
        output_path=output_dir / "resources.csv",
    ):
        with log_path.open("w", encoding="utf-8") as log_file:
            completed = subprocess.run(
                command,
                cwd=root,
                env=run_environment,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=expected_duration + 240,
            )
    if completed.returncode != 0:
        tail = "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-40:])
        raise RuntimeError(f"Locust master failed with exit code {completed.returncode}:\n{tail}")
    result_path = output_dir / "result.json"
    if not result_path.is_file():
        raise RuntimeError(f"Locust master did not write {result_path}")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "mode": "distributed",
        "expected_workers": expected_workers,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "profile_path": str(profile_path),
        "profile_sha256": profile_sha256(profile_path),
        "data_file_sha256": profile_sha256(data_file),
        "result_path": str(result_path),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _run_worker(
    root: Path,
    environment: dict[str, str],
    *,
    master_host: str,
    log_path: Path,
) -> int:
    command = _worker_command(root, master_host=master_host)
    worker_environment = environment.copy()
    worker_environment["QA_PERF_WORKER"] = "1"
    with log_path.open("w", encoding="utf-8") as log_file:
        completed = subprocess.run(
            command,
            cwd=root,
            env=worker_environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return completed.returncode


def _worker_command(root: Path, *, master_host: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(root / "performance" / "locustfiles" / "api_journeys.py"),
        "--worker",
        "--master-host",
        master_host,
    ]


def _environment(root: Path, profile_path: Path, data_file: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = f"{root / 'packages'}{os.pathsep}{root}" + (
        f"{os.pathsep}{environment['PYTHONPATH']}" if environment.get("PYTHONPATH") else ""
    )
    environment["QA_PERF_PROFILE"] = str(profile_path)
    environment["QA_PERF_DATA_FILE"] = str(data_file)
    return environment


if __name__ == "__main__":
    raise SystemExit(main())
