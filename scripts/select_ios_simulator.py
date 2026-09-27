"""Select an available iOS Simulator UDID from `simctl list` JSON."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def select_simulator(
    payload: dict[str, Any],
    device_name: str,
    fallback_prefix: str | None,
) -> tuple[str, str] | None:
    """Return an exact match first, then an available fallback device."""

    available: list[tuple[str, str]] = []
    for devices in payload.get("devices", {}).values():
        for device in devices:
            if not device.get("isAvailable"):
                continue
            name = str(device.get("name", ""))
            udid = str(device.get("udid", ""))
            if not udid:
                continue
            available.append((name, udid))
            if name == device_name:
                return name, udid

    if fallback_prefix:
        for name, udid in available:
            if name.startswith(fallback_prefix):
                return name, udid
    return None


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-name", required=True)
    parser.add_argument(
        "--fallback-prefix",
        help="Fallback device name prefix when the preferred device is unavailable.",
    )
    return parser.parse_args()


def main() -> int:
    """Read simctl JSON from stdin and print the selected UDID."""

    args = parse_args()
    payload = json.load(sys.stdin)
    selected = select_simulator(payload, args.device_name, args.fallback_prefix)
    if selected is None:
        print(f"No available simulator matched {args.device_name!r}.", file=sys.stderr)
        return 1

    name, udid = selected
    print(udid)
    print(f"Selected simulator: {name} ({udid})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
