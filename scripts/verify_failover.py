"""Restart isolated dependencies and verify API recovery."""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class Probe:
    """One request probe during a restart window."""

    elapsed_seconds: float
    live_status: int | None
    ready_status: int | None
    live_error: str | None
    ready_error: str | None


@dataclass(frozen=True)
class RecoveryResult:
    """Recovery evidence for one service restart."""

    service: str
    restart_started_at: str
    restart_return_code: int
    probes: int
    failed_probes: int
    first_failure_seconds: float | None
    recovery_seconds: float | None
    final_live_status: int | None
    final_ready_status: int | None
    passed: bool


def probe_once(client: httpx.Client, elapsed: float) -> Probe:
    """Probe liveness and readiness without failing the sampler."""

    live_status: int | None = None
    ready_status: int | None = None
    live_error: str | None = None
    ready_error: str | None = None
    try:
        live_status = client.get("/health/live").status_code
    except httpx.HTTPError as exc:
        live_error = type(exc).__name__
    try:
        ready_status = client.get("/health/ready").status_code
    except httpx.HTTPError as exc:
        ready_error = type(exc).__name__
    return Probe(
        elapsed_seconds=elapsed,
        live_status=live_status,
        ready_status=ready_status,
        live_error=live_error,
        ready_error=ready_error,
    )


def restart_service(
    *,
    service: str,
    project: str,
    compose_file: Path,
    env_file: Path,
) -> int:
    """Restart one service inside the explicit isolated Compose project."""

    command = [
        "docker",
        "compose",
        "--profile",
        "monitoring",
        "--env-file",
        str(env_file),
        "-p",
        project,
        "-f",
        str(compose_file),
        "restart",
        service,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"restart {service} failed: {detail}")
    return completed.returncode


def verify_restart(
    *,
    service: str,
    api_base_url: str,
    project: str,
    compose_file: Path,
    env_file: Path,
    wait_seconds: float,
) -> RecoveryResult:
    """Restart one service while probing health and wait for full recovery."""

    probes: list[Probe] = []
    stop = threading.Event()
    started = time.monotonic()

    with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=1.0) as client:
        preflight = probe_once(client, 0.0)
        if preflight.live_status != 200 or preflight.ready_status != 200:
            raise RuntimeError(f"API is not ready before restarting {service}: {preflight}")

        def sample() -> None:
            while not stop.is_set():
                probes.append(probe_once(client, time.monotonic() - started))
                time.sleep(0.2)

        thread = threading.Thread(target=sample, daemon=True)
        thread.start()
        restart_started = datetime.now(UTC).isoformat()
        return_code = restart_service(
            service=service,
            project=project,
            compose_file=compose_file,
            env_file=env_file,
        )
        recovered_at: float | None = None
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            current = probe_once(client, time.monotonic() - started)
            if current.live_status == 200 and current.ready_status == 200:
                recovered_at = current.elapsed_seconds
                break
            time.sleep(0.25)
        stop.set()
        thread.join(timeout=5)
        final = probe_once(client, time.monotonic() - started)

    failures = [
        probe
        for probe in probes
        if probe.live_status != 200 or probe.ready_status != 200
    ]
    first_failure = failures[0].elapsed_seconds if failures else None
    passed = (
        bool(failures)
        and recovered_at is not None
        and final.live_status == 200
        and final.ready_status == 200
    )
    return RecoveryResult(
        service=service,
        restart_started_at=restart_started,
        restart_return_code=return_code,
        probes=len(probes),
        failed_probes=len(failures),
        first_failure_seconds=first_failure,
        recovery_seconds=recovered_at,
        final_live_status=final.live_status,
        final_ready_status=final.ready_status,
        passed=passed,
    )


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:28000")
    parser.add_argument("--project", default="quality-engineering-lab-performance")
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
    parser.add_argument("--service", action="append", dest="services")
    parser.add_argument("--wait-seconds", type=float, default=90.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=root
        / "artifacts"
        / "performance"
        / "week29"
        / "week29-soak"
        / "failover.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    services = args.services or ["redis", "postgres", "api"]
    results = [
        asdict(
            verify_restart(
                service=service,
                api_base_url=args.api_base_url,
                project=args.project,
                compose_file=args.compose_file.resolve(),
                env_file=args.env_file.resolve(),
                wait_seconds=max(args.wait_seconds, 5.0),
            )
        )
        for service in services
    ]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "api_base_url": args.api_base_url,
        "project": args.project,
        "results": results,
        "passed": all(result["passed"] for result in results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Evidence: {args.output.resolve()}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
