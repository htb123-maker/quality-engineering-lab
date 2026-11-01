"""Select parallel and optional compatibility iOS Simulators."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_IOS_RUNTIME_PATTERN = re.compile(r"iOS-(?P<major>\d+)-(?P<minor>\d+)")


@dataclass(frozen=True, slots=True)
class SimulatorDevice:
    """One available iOS Simulator."""

    name: str
    udid: str
    version: str
    major: int


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="JSON output from xcrun simctl list devices available -j",
    )
    parser.add_argument(
        "--output-env",
        type=Path,
        help="Write GitHub Actions environment assignments to this file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the selected matrix as JSON.",
    )
    return parser.parse_args(argv)


def load_devices(payload: object) -> tuple[SimulatorDevice, ...]:
    """Extract available iPhone Simulators from simctl JSON."""

    if not isinstance(payload, dict):
        raise ValueError("simctl payload must be a JSON object")
    runtimes = payload.get("devices")
    if not isinstance(runtimes, dict):
        raise ValueError("simctl payload must contain devices")

    selected: list[SimulatorDevice] = []
    for runtime_key, devices in runtimes.items():
        if not isinstance(runtime_key, str) or not isinstance(devices, list):
            continue
        match = _IOS_RUNTIME_PATTERN.search(runtime_key)
        if match is None:
            continue
        major = int(match.group("major"))
        minor = int(match.group("minor"))
        version = f"{major}.{minor}"
        for device in devices:
            if not isinstance(device, dict):
                continue
            name = device.get("name")
            udid = device.get("udid")
            available = device.get("isAvailable", device.get("state") == "Available")
            if (
                available is True
                and isinstance(name, str)
                and name.startswith("iPhone")
                and isinstance(udid, str)
                and udid
            ):
                selected.append(
                    SimulatorDevice(
                        name=name,
                        udid=udid,
                        version=version,
                        major=major,
                    )
                )
    if not selected:
        raise ValueError("no available iPhone Simulator was found")
    return tuple(selected)


def select_matrix(
    devices: tuple[SimulatorDevice, ...],
    *,
    preferred_names: Sequence[str] = ("iPhone 16", "iPhone 15", "iPhone 14"),
) -> dict[str, dict[str, str]]:
    """Choose two current-major devices plus an optional prior-major device."""

    current_major = max(device.major for device in devices)
    current = sorted(
        (device for device in devices if device.major == current_major),
        key=lambda device: _preference_key(device, preferred_names),
    )
    if len(current) < 2:
        raise ValueError(
            f"iOS {current_major} has {len(current)} available iPhone; "
            "parallel acceptance requires at least two"
        )

    matrix: dict[str, dict[str, str]] = {
        "current": {
            "device": current[0].name,
            "udid": current[0].udid,
            "version": current[0].version,
        },
        "secondary": {
            "device": current[1].name,
            "udid": current[1].udid,
            "version": current[1].version,
        },
    }

    previous_majors = sorted(
        {device.major for device in devices if device.major < current_major},
        reverse=True,
    )
    if previous_majors:
        previous_major = previous_majors[0]
        previous = sorted(
            (device for device in devices if device.major == previous_major),
            key=lambda device: _preference_key(device, preferred_names),
        )[0]
        matrix["previous"] = {
            "device": previous.name,
            "udid": previous.udid,
            "version": previous.version,
        }
    return matrix


def environment_lines(matrix: dict[str, dict[str, str]]) -> tuple[str, ...]:
    """Render GitHub Actions env-file assignments."""

    lines: list[str] = []
    names = {
        "current": "CURRENT",
        "secondary": "SECONDARY",
        "previous": "PREVIOUS",
    }
    for key, prefix in names.items():
        profile = matrix.get(key)
        if profile is None:
            continue
        lines.extend(
            (
                f"QA_IOS_SIM_{prefix}_DEVICE={profile['device']}",
                f"QA_IOS_SIM_{prefix}_VERSION={profile['version']}",
                f"QA_IOS_SIM_{prefix}_UDID={profile['udid']}",
            )
        )
    lines.append(
        "QA_IOS_SIM_PREVIOUS_AVAILABLE="
        f"{str('previous' in matrix).lower()}"
    )
    return tuple(lines)


def _preference_key(
    device: SimulatorDevice,
    preferred_names: Sequence[str],
) -> tuple[int, str, str]:
    try:
        preference = preferred_names.index(device.name)
    except ValueError:
        preference = len(preferred_names)
    return preference, device.name, device.udid


def main(argv: Sequence[str] | None = None) -> int:
    """Select devices, print evidence, and optionally write an env file."""

    args = parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        matrix = select_matrix(load_devices(payload))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc

    if args.output_env is not None:
        args.output_env.write_text(
            "\n".join(environment_lines(matrix)) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(matrix, indent=2, sort_keys=True))
    else:
        for key, profile in matrix.items():
            print(
                f"{key}: {profile['device']} / iOS {profile['version']} / "
                f"{profile['udid']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
