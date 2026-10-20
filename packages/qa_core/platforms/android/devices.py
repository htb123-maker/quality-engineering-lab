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
    """Load selected devices from YAML and resolve environment overrides."""

    env = dict(os.environ if environment is None else environment)
    selected_ids = _selected_device_ids(env)
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

    configured_ids: set[str] = set()
    resolved: list[AndroidDeviceProfile] = []
    for index, device in enumerate(devices):
        if not isinstance(device, Mapping):
            raise ValueError(f"device entry {index} must be a mapping")
        device_id = _required_string(device, "id", index)
        if device_id in configured_ids:
            raise ValueError(f"duplicate Android device id: {device_id!r}")
        configured_ids.add(device_id)
        role = _required_string(device, "role", index)
        udid_env = _required_string(device, "udid_env", index)
        default_udid = _optional_string(device, "default_udid", index)
        platform_version_env = _optional_string(device, "platform_version_env", index)
        platform_version = _optional_string(device, "platform_version", index)
        platform_version = env.get(platform_version_env, "").strip() or platform_version
        required = device.get("required", False)
        if not isinstance(required, bool):
            raise ValueError(f"device entry {index} required must be boolean")

        selected = not selected_ids or device_id in selected_ids
        udid = env.get(udid_env, "").strip() or default_udid
        if not udid:
            if (selected_ids and selected) or (not selected_ids and required):
                raise ValueError(
                    f"selected Android device {device_id!r} has no UDID; "
                    f"set {udid_env}"
                )
            continue
        if not selected:
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

    unknown_ids = selected_ids.difference(configured_ids)
    if unknown_ids:
        raise ValueError(
            "QA_ANDROID_DEVICE_IDS contains unknown device id(s): "
            f"{', '.join(sorted(unknown_ids))}"
        )
    if not resolved:
        raise ValueError("Android device matrix resolved no usable devices")
    udids = [profile.udid for profile in resolved]
    if len(udids) != len(set(udids)):
        raise ValueError("Android device matrix contains duplicate UDIDs")
    return tuple(resolved)


def _selected_device_ids(environment: Mapping[str, str]) -> set[str]:
    """Return explicitly selected profile IDs, or an empty set for all devices."""

    raw_ids = environment.get("QA_ANDROID_DEVICE_IDS", "").strip()
    if not raw_ids:
        return set()
    selected = {value.strip() for value in raw_ids.split(",") if value.strip()}
    if not selected:
        raise ValueError("QA_ANDROID_DEVICE_IDS must contain at least one device id")
    return selected


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
