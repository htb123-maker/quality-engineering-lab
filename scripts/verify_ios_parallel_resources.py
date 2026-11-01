"""Verify that parallel iOS workers used isolated, overlapping resources."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-workers", type=int, required=True)
    return parser.parse_args(argv)


def verify_records(
    run_dir: Path,
    expected_workers: int,
) -> dict[str, Any]:
    """Validate worker count, unique resources, and session overlap."""

    if expected_workers < 1:
        raise ValueError("expected-workers must be at least one")
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(run_dir.glob("*.json"))
    ]
    if len(records) != expected_workers:
        raise ValueError(
            f"expected {expected_workers} worker records, found {len(records)}"
        )
    if not all(record.get("completed") is True for record in records):
        raise ValueError("one or more iOS workers did not complete")

    for field in ("device_id", "udid", "wda_local_port", "derived_data_path"):
        values = [record.get(field) for record in records]
        if any(value in (None, "") for value in values):
            raise ValueError(f"worker record is missing {field}")
        if len(values) != len(set(values)):
            raise ValueError(f"parallel iOS workers share {field}: {values!r}")

    starts = [float(record["started_at"]) for record in records]
    ends = [float(record["ended_at"]) for record in records]
    if max(starts) >= min(ends):
        raise ValueError("iOS worker sessions did not overlap in time")

    return {
        "worker_count": len(records),
        "devices": sorted(str(record["device_id"]) for record in records),
        "wda_local_ports": sorted(int(record["wda_local_port"]) for record in records),
        "derived_data_paths": sorted(
            str(record["derived_data_path"]) for record in records
        ),
        "overlap_seconds": min(ends) - max(starts),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Validate and print the parallel-resource summary."""

    args = parse_args(argv)
    try:
        summary = verify_records(args.run_dir, args.expected_workers)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
