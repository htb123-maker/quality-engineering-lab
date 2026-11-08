"""Sample Docker container resources for a bounded performance run."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

_SIZE_PATTERN = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\s*([A-Za-z]+)\s*$"
)
_SIZE_MULTIPLIERS = {
    "B": 1,
    "KB": 1_000,
    "MB": 1_000_000,
    "GB": 1_000_000_000,
    "TB": 1_000_000_000_000,
    "KIB": 1_024,
    "MIB": 1_024**2,
    "GIB": 1_024**3,
    "TIB": 1_024**4,
}


@dataclass(frozen=True)
class ResourceSample:
    """One point-in-time resource reading for one Compose service."""

    timestamp: str
    run_id: str
    profile: str
    service: str
    cpu_percent: float
    memory_usage_bytes: int
    memory_limit_bytes: int
    network_io_bytes: int
    block_io_bytes: int


def parse_size(value: str) -> int:
    """Parse Docker's human-readable byte units into bytes."""

    match = _SIZE_PATTERN.match(value)
    if match is None:
        raise ValueError(f"unsupported Docker size: {value!r}")
    amount = float(match.group(1))
    unit = match.group(2).upper()
    multiplier = _SIZE_MULTIPLIERS.get(unit)
    if multiplier is None:
        raise ValueError(f"unsupported Docker size unit: {unit!r}")
    return int(amount * multiplier)


def parse_percent(value: str) -> float:
    """Parse a Docker percentage such as ``1.25%``."""

    return float(value.strip().removesuffix("%"))


def parse_io_pair(value: str) -> int:
    """Parse Docker's ``received / sent`` or ``read / write`` pair."""

    parts = value.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"unsupported Docker I/O pair: {value!r}")
    return sum(parse_size(part) for part in parts)


class DockerResourceSampler:
    """Write container CPU, memory, network, and block I/O samples to CSV."""

    def __init__(
        self,
        *,
        root: Path,
        project: str,
        env_file: Path,
        compose_file: Path,
        run_id: str,
        profile: str,
        output_path: Path,
        interval_seconds: float = 2.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("resource sample interval must be positive")
        self._root = root
        self._project = project
        self._env_file = env_file
        self._compose_file = compose_file
        self._run_id = run_id
        self._profile = profile
        self._output_path = output_path
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._containers: dict[str, str] = {}
        self._file_handle: Any = None
        self._writer: csv.DictWriter[str] | None = None

    def __enter__(self) -> Self:
        self._containers = self._compose_containers()
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_handle = self._output_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(
            self._file_handle,
            fieldnames=list(asdict(self._empty_sample("api")).keys()),
        )
        self._writer.writeheader()
        self._write_samples()
        self._thread = threading.Thread(
            target=self._sample_loop,
            name="performance-resource-sampler",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self._file_handle is not None:
            self._file_handle.close()
        if exc_type is None and self._error is not None:
            raise RuntimeError("Docker resource sampling failed") from self._error

    def _sample_loop(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._write_samples()
            except BaseException as error:
                self._error = error
                self._stop.set()
                return

    def _write_samples(self) -> None:
        for sample in self.sample_once():
            if self._writer is None:
                raise RuntimeError("resource sampler output is not initialized")
            self._writer.writerow(asdict(sample))
        if self._file_handle is None:
            raise RuntimeError("resource sampler output file is not initialized")
        self._file_handle.flush()

    def sample_once(self) -> tuple[ResourceSample, ...]:
        """Read one sample for every required Compose service."""

        container_ids = list(self._containers.values())
        if not container_ids:
            raise RuntimeError("no Compose service containers were found")
        command = [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            *container_ids,
        ]
        completed = subprocess.run(
            command,
            cwd=self._root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"docker stats failed: {completed.stderr.strip() or completed.stdout.strip()}"
            )

        samples: list[ResourceSample] = []
        id_to_service = {
            container_id[:12]: service for service, container_id in self._containers.items()
        }
        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            payload: Any = json.loads(line)
            if not isinstance(payload, dict):
                continue
            container_id = str(payload.get("ID", ""))[:12]
            service = id_to_service.get(container_id)
            if service is None:
                continue
            memory_parts = str(payload.get("MemUsage", "")).split("/", 1)
            if len(memory_parts) != 2:
                raise ValueError(
                    f"unsupported memory usage for {service}: {payload.get('MemUsage')!r}"
                )
            samples.append(
                ResourceSample(
                    timestamp=datetime.now(UTC).isoformat(),
                    run_id=self._run_id,
                    profile=self._profile,
                    service=service,
                    cpu_percent=parse_percent(str(payload.get("CPUPerc", "0%"))),
                    memory_usage_bytes=parse_size(memory_parts[0]),
                    memory_limit_bytes=parse_size(memory_parts[1]),
                    network_io_bytes=parse_io_pair(str(payload.get("NetIO", "0B / 0B"))),
                    block_io_bytes=parse_io_pair(str(payload.get("BlockIO", "0B / 0B"))),
                )
            )
        if {sample.service for sample in samples} != set(self._containers):
            missing = sorted(set(self._containers) - {sample.service for sample in samples})
            raise RuntimeError(f"docker stats omitted services: {', '.join(missing)}")
        return tuple(samples)

    def _compose_containers(self) -> dict[str, str]:
        command = [
            "docker",
            "compose",
            "-p",
            self._project,
            "--env-file",
            str(self._env_file),
            "-f",
            str(self._compose_file),
            "ps",
            "--format",
            "json",
        ]
        completed = subprocess.run(
            command,
            cwd=self._root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"docker compose ps failed: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        payloads = _parse_compose_payloads(completed.stdout)
        containers = {
            str(payload["Service"]): str(payload["ID"])
            for payload in payloads
            if "Service" in payload and "ID" in payload
        }
        required = {"api", "postgres", "redis"}
        missing = sorted(required - set(containers))
        if missing:
            raise RuntimeError(f"required Compose services are not running: {', '.join(missing)}")
        return containers

    def _empty_sample(self, service: str) -> ResourceSample:
        return ResourceSample(
            timestamp="",
            run_id=self._run_id,
            profile=self._profile,
            service=service,
            cpu_percent=0.0,
            memory_usage_bytes=0,
            memory_limit_bytes=0,
            network_io_bytes=0,
            block_io_bytes=0,
        )


def _parse_compose_payloads(output: str) -> list[dict[str, Any]]:
    stripped = output.strip()
    if not stripped:
        return []
    try:
        payload: Any = json.loads(stripped)
    except json.JSONDecodeError:
        payloads = [json.loads(line) for line in stripped.splitlines() if line.strip()]
        return [item for item in payloads if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []
