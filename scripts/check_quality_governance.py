"""Validate quality owners and quarantine expiration."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from qa_core.reporting import load_quality_governance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/quality-governance.yaml"),
    )
    parser.add_argument("--today", type=date.fromisoformat)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    governance = load_quality_governance(
        args.config,
        today=args.today or date.today(),
    )
    print(
        f"quality governance valid: {len(governance.quarantine)} quarantined tests"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
