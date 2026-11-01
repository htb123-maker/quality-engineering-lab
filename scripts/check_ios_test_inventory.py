"""Validate the 50-item Week 21 iOS inventory against pytest source files."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from qa_core.platforms.ios.inventory import load_ios_test_inventory

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse inventory path and output options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=PROJECT_ROOT / "configs" / "ios-test-inventory.yaml",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Load the inventory and print its validated summary."""

    args = parse_args(argv)
    try:
        inventory = load_ios_test_inventory(
            args.inventory,
            project_root=PROJECT_ROOT,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    summary = {
        "expected_count": inventory.expected_count,
        "actual_count": len(inventory.tests),
        "priorities": {
            priority.value: count
            for priority, count in sorted(inventory.priorities().items())
        },
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            f"iOS inventory valid: {summary['actual_count']} unique tests "
            f"({summary['priorities']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
