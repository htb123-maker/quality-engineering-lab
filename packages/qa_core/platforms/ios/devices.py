"""iOS device-matrix loading, worker binding, and resource isolation."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from qa_core.config.settings import Settings

_WORKER_PATTERN = re.compile(r"^gw(?P<index>\d+)$")
_SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DEVICE_PROVIDERS = {"local", "browserstack", "saucelabs", "lambdatest"}
_CAPABILITY_PROFILES = {"simulator", "device"}


@dataclass(frozen=True, slots=True)
class IosDeviceProfile:
    """One resolved simulator or cloud-device profile."""

    device_id: str
    role: str
    provider: str
    capability_profile: str
    device_name: str
    platform_version: str
    udid: str | None
    required: bool

    def __post_init__(self) -> None:
        _require_safe_token(self.device_id, "device id")
        _require_non_empty(self.role, "device role")
        _require_non_empty(self.device_name, "device name")
        _require_non_empty(self.platform_version, "platform version")
        if self.provider not in _DEVICE_PROVIDERS:
            raise ValueError(f"unsupported iOS device provider: {self.provider!r}")
        if self.capability_profile not in _CAPABILITY_PROFILES:
            raise ValueError(
                f"unsupported iOS capability profile: {self.capability_profile!r}"
            )
        if self.provider == "local" and not self.udid:
            raise ValueError(f"local iOS device {self.device_id!r} requires a UDID")


@dataclass(frozen=True, slots=True)
class IosDeviceMatrix:
    """Resolved iOS devices plus matrix-level resource defaults."""

    profiles: tuple[IosDeviceProfile, ...]
    appium_port_base: int
    wda_port_base: int
    derived_data_root: Path

    def __post_init__(self) -> None:
        if not self.profiles:
            raise ValueError("iOS device matrix must resolve at least one device")
        if not 1024 <= self.appium_port_base <= 65535:
            raise ValueError("iOS Appium port base must be between 1024 and 65535")
        if not 1024 <= self.wda_port_base <= 65535:
            raise ValueError("iOS WDA port base must be between 1024 and 65535")
        if self.derived_data_root.is_absolute():
            raise ValueError("iOS derived-data root must be project-relative")
        if ".." in self.derived_data_root.parts:
            raise ValueError("iOS derived-data root must not contain '..'")


@dataclass(frozen=True, slots=True)
class IosWorkerResources:
    """Resources reserved for one serial or xdist worker."""

    profile: IosDeviceProfile
    worker_index: int
    worker_count: int
    run_id: str
    appium_server_port: int | None
    wda_local_port: int | None
    derived_data_path: Path


def load_ios_device_matrix(
    matrix_path: Path,
    environment: Mapping[str, str] | None = None,
) -> IosDeviceMatrix:
    """Load selected iOS profiles and resolve environment overrides."""

    env = dict(os.environ if environment is None else environment)
    try:
        payload = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"iOS device matrix not found: {matrix_path}") from exc

    if not isinstance(payload, Mapping):
        raise ValueError("iOS device matrix must be a YAML mapping")
    if payload.get("version") != 1:
        raise ValueError("iOS device matrix version must be 1")

    raw_appium_port = payload.get("appium_port_base", 4723)
    if isinstance(raw_appium_port, bool) or not isinstance(raw_appium_port, int):
        raise ValueError("iOS Appium port base must be an integer")
    raw_wda_port = payload.get("wda_port_base", 8100)
    if isinstance(raw_wda_port, bool) or not isinstance(raw_wda_port, int):
        raise ValueError("iOS WDA port base must be an integer")

    raw_root = payload.get("derived_data_root", "artifacts/ios-derived")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise ValueError("iOS derived-data root must be a non-empty string")

    devices = payload.get("devices")
    if not isinstance(devices, list) or not devices:
        raise ValueError("iOS device matrix must contain at least one device")

    selected_ids = _selected_device_ids(env)
    configured_ids: set[str] = set()
    resolved: list[IosDeviceProfile] = []
    for index, device in enumerate(devices):
        if not isinstance(device, Mapping):
            raise ValueError(f"device entry {index} must be a mapping")

        device_id = _required_string(device, "id", index)
        if device_id in configured_ids:
            raise ValueError(f"duplicate iOS device id: {device_id!r}")
        configured_ids.add(device_id)

        required = _required_bool(device, "required", index)
        selected = not selected_ids or device_id in selected_ids
        if not selected:
            continue

        role = _required_string(device, "role", index)
        provider = _required_string(device, "provider", index)
        capability_profile = _required_string(device, "capability_profile", index)
        device_name_env = _required_string(device, "device_name_env", index)
        device_name = env.get(device_name_env, "").strip() or _optional_string(
            device,
            "default_device_name",
            index,
        )
        platform_version_env = _optional_string(device, "platform_version_env", index)
        platform_version = env.get(platform_version_env, "").strip() or _optional_string(
            device,
            "default_platform_version",
            index,
        )
        udid_env = _optional_string(device, "udid_env", index)
        udid = env.get(udid_env, "").strip() or _optional_string(
            device,
            "default_udid",
            index,
        )

        missing: list[str] = []
        if not device_name:
            missing.append(device_name_env)
        if not platform_version:
            missing.append(platform_version_env or "platform_version")
        if provider == "local" and not udid:
            missing.append(udid_env or "udid")
        if missing:
            if selected_ids or required:
                raise ValueError(
                    f"selected iOS device {device_id!r} has missing value(s): "
                    f"{', '.join(missing)}"
                )
            continue

        resolved.append(
            IosDeviceProfile(
                device_id=device_id,
                role=role,
                provider=provider,
                capability_profile=capability_profile,
                device_name=device_name,
                platform_version=platform_version,
                udid=udid or None,
                required=required,
            )
        )

    unknown_ids = selected_ids.difference(configured_ids)
    if unknown_ids:
        raise ValueError(
            "QA_IOS_DEVICE_IDS contains unknown device id(s): "
            f"{', '.join(sorted(unknown_ids))}"
        )
    if not resolved:
        raise ValueError("iOS device matrix resolved no usable devices")

    udids = [profile.udid for profile in resolved if profile.udid]
    if len(udids) != len(set(udids)):
        raise ValueError("iOS device matrix contains duplicate UDIDs")

    return IosDeviceMatrix(
        profiles=tuple(resolved),
        appium_port_base=raw_appium_port,
        wda_port_base=raw_wda_port,
        derived_data_root=Path(raw_root.strip()),
    )


def select_ios_worker_device(
    profiles: tuple[IosDeviceProfile, ...],
    worker_id: str,
    worker_count: int,
) -> IosDeviceProfile:
    """Assign one xdist worker to one iOS profile without sharing a device."""

    worker_index = _worker_index(worker_id, worker_count)
    if worker_count > len(profiles):
        raise ValueError(
            f"pytest requested {worker_count} workers but the iOS matrix has "
            f"{len(profiles)} active device(s)"
        )
    return profiles[worker_index]


def allocate_ios_worker_resources(
    matrix: IosDeviceMatrix,
    worker_id: str,
    worker_count: int,
    project_root: Path,
    environment: Mapping[str, str] | None = None,
) -> IosWorkerResources:
    """Reserve one device, WDA port, and DerivedData directory for a worker."""

    env = dict(os.environ if environment is None else environment)
    worker_index = _worker_index(worker_id, worker_count)
    profile = select_ios_worker_device(matrix.profiles, worker_id, worker_count)

    run_id = (
        env.get("QA_IOS_RUN_ID", "").strip()
        or env.get("GITHUB_RUN_ID", "").strip()
        or "local"
    )
    _require_safe_token(run_id, "iOS run id")

    appium_server_port: int | None = None
    wda_local_port: int | None = None
    if profile.provider == "local":
        appium_server_port = matrix.appium_port_base + worker_index
        wda_local_port = matrix.wda_port_base + worker_index
        if appium_server_port > 65535:
            raise ValueError("allocated iOS Appium port exceeds 65535")
        if wda_local_port > 65535:
            raise ValueError("allocated iOS WDA port exceeds 65535")

    root = project_root.resolve()
    derived_data_path = (
        root / matrix.derived_data_root / run_id / profile.device_id
    ).resolve()
    if not derived_data_path.is_relative_to(root):
        raise ValueError("allocated iOS DerivedData path escapes the project root")

    return IosWorkerResources(
        profile=profile,
        worker_index=worker_index,
        worker_count=worker_count,
        run_id=run_id,
        appium_server_port=appium_server_port,
        wda_local_port=wda_local_port,
        derived_data_path=derived_data_path,
    )


def build_ios_worker_settings(
    settings: Settings,
    profile: IosDeviceProfile,
    resources: IosWorkerResources,
) -> Settings:
    """Return settings targeting exactly one resolved matrix profile."""

    updates: dict[str, object] = {
        "ios_device_provider": profile.provider,
        "ios_capability_profile": profile.capability_profile,
        "ios_device_name": profile.device_name,
        "ios_platform_version": profile.platform_version,
        "ios_udid": profile.udid,
        "ios_derived_data_path": resources.derived_data_path,
    }
    if profile.provider == "local":
        updates["appium_server_url"] = (
            f"http://127.0.0.1:{resources.appium_server_port}"
        )
        updates["ios_wda_local_port"] = resources.wda_local_port
    else:
        updates["ios_cloud_device_name"] = profile.device_name
        updates["ios_cloud_platform_version"] = profile.platform_version
        updates["ios_derived_data_path"] = None
    return settings.model_copy(update=updates)


def ios_xdist_worker_context(
    environment: Mapping[str, str] | None = None,
) -> tuple[str, int, int]:
    """Return worker id, zero-based index, and worker count."""

    env = dict(os.environ if environment is None else environment)
    worker_id = env.get("PYTEST_XDIST_WORKER", "gw0")
    raw_count = env.get("PYTEST_XDIST_WORKER_COUNT", "1")
    try:
        count = int(raw_count)
    except ValueError as exc:
        raise ValueError(
            f"invalid PYTEST_XDIST_WORKER_COUNT value: {raw_count}"
        ) from exc
    index = _worker_index(worker_id, count)
    return worker_id, index, count


def _selected_device_ids(environment: Mapping[str, str]) -> set[str]:
    raw_ids = environment.get("QA_IOS_DEVICE_IDS", "").strip()
    if not raw_ids:
        return set()
    selected = {value.strip() for value in raw_ids.split(",") if value.strip()}
    if not selected:
        raise ValueError("QA_IOS_DEVICE_IDS must contain at least one device id")
    return selected


def _worker_index(worker_id: str, worker_count: int) -> int:
    if worker_count < 1:
        raise ValueError("worker count must be at least one")
    match = _WORKER_PATTERN.fullmatch(worker_id)
    if match is None:
        raise ValueError(f"invalid xdist worker id: {worker_id}")
    index = int(match.group("index"))
    if index >= worker_count:
        raise ValueError(
            f"xdist worker {worker_id} is outside configured worker count {worker_count}"
        )
    return index


def _required_string(
    device: Mapping[object, object],
    key: str,
    index: int,
) -> str:
    value = device.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"device entry {index} {key} must be a non-empty string")
    return value.strip()


def _optional_string(
    device: Mapping[object, object],
    key: str,
    index: int,
) -> str:
    value = device.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"device entry {index} {key} must be a string")
    return value.strip()


def _required_bool(
    device: Mapping[object, object],
    key: str,
    index: int,
) -> bool:
    value = device.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"device entry {index} {key} must be boolean")
    return value


def _require_non_empty(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")


def _require_safe_token(value: str, label: str) -> None:
    if _SAFE_TOKEN_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{label} must contain only letters, digits, dots, underscores, or hyphens"
        )
