"""Android device-matrix loading and pytest-worker assignment."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

_WORKER_PATTERN = re.compile(r"^gw(?P<index>\d+)$")


@dataclass(frozen=True, slots=True)
class AndroidDeviceProfile:
    """One configured Android device and its intended test role."""

    device_id: str
    role: str
    udid: str
    platform_version: str
    required: bool

    def __post_init__(self) -> None:
        if not self.device_id.strip():
            raise ValueError("device id must not be empty")
        if not self.role.strip():
            raise ValueError("device role must not be empty")
        if not self.udid.strip():
            raise ValueError("device udid must not be empty")


def load_android_device_matrix(
    matrix_path: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[AndroidDeviceProfile, ...]:
    """Load active devices from YAML and resolve UDID environment overrides."""

    env = dict(os.environ if environment is None else environment)
    try:
        payload = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Android device matrix not found: {matrix_path}") from exc

    if not isinstance(payload, Mapping):
        raise ValueError("Android device matrix must be a YAML mapping")
    if payload.get("version") != 1:
        raise ValueError("Android device matrix version must be 1")
    devices = payload.get("devices")
    if not isinstance(devices, list) or not devices:
        raise ValueError("Android device matrix must contain at least one device")

    resolved: list[AndroidDeviceProfile] = []
    for index, device in enumerate(devices):
        if not isinstance(device, Mapping):
            raise ValueError(f"device entry {index} must be a mapping")
        device_id = _required_string(device, "id", index)
        role = _required_string(device, "role", index)
        udid_env = _required_string(device, "udid_env", index)
        default_udid = _optional_string(device, "default_udid", index)
        platform_version = _optional_string(device, "platform_version", index)
        required = device.get("required", False)
        if not isinstance(required, bool):
            raise ValueError(f"device entry {index} required must be boolean")

        udid = env.get(udid_env, "").strip() or default_udid
        if not udid:
            if required:
                raise ValueError(
                    f"required Android device {device_id!r} has no UDID; "
                    f"set {udid_env}"
                )
            continue
        resolved.append(
            AndroidDeviceProfile(
                device_id=device_id,
                role=role,
                udid=udid,
                platform_version=platform_version,
                required=required,
            )
        )

    if not resolved:
        raise ValueError("Android device matrix resolved no usable devices")
    udids = [profile.udid for profile in resolved]
    if len(udids) != len(set(udids)):
        raise ValueError("Android device matrix contains duplicate UDIDs")
    return tuple(resolved)


def select_worker_device(
    profiles: tuple[AndroidDeviceProfile, ...],
    worker_id: str,
    worker_count: int,
) -> AndroidDeviceProfile:
    """Assign one xdist worker to one device without sharing a device."""

    if worker_count < 1:
        raise ValueError("worker count must be at least one")
    if worker_count > len(profiles):
        raise ValueError(
            f"pytest requested {worker_count} workers but the matrix has "
            f"{len(profiles)} active device(s)"
        )
    match = _WORKER_PATTERN.fullmatch(worker_id)
    if match is None:
        raise ValueError(f"invalid xdist worker id: {worker_id}")
    index = int(match.group("index"))
    if index >= worker_count:
        raise ValueError(
            f"xdist worker {worker_id} is outside configured worker count {worker_count}"
        )
    return profiles[index]


def xdist_worker_context(environment: Mapping[str, str] | None = None) -> tuple[int, int]:
    """Return the current worker index and worker count for xdist or serial runs."""

    env = dict(os.environ if environment is None else environment)
    worker_id = env.get("PYTEST_XDIST_WORKER", "gw0")
    match = _WORKER_PATTERN.fullmatch(worker_id)
    if match is None:
        raise ValueError(f"invalid PYTEST_XDIST_WORKER value: {worker_id}")
    index = int(match.group("index"))
    raw_count = env.get("PYTEST_XDIST_WORKER_COUNT", "1")
    try:
        count = int(raw_count)
    except ValueError as exc:
        raise ValueError(
            f"invalid PYTEST_XDIST_WORKER_COUNT value: {raw_count}"
        ) from exc
    if count < 1 or index >= count:
        raise ValueError(
            f"worker {worker_id} is outside PYTEST_XDIST_WORKER_COUNT={count}"
        )
    return index, count


def _required_string(device: Mapping[object, object], key: str, index: int) -> str:
    value = device.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"device entry {index} {key} must be a non-empty string")
    return value.strip()


def _optional_string(device: Mapping[object, object], key: str, index: int) -> str:
    value = device.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"device entry {index} {key} must be a string")
    return value.strip()
