"""Build each worker's WDA cache sequentially before parallel sessions."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver
from qa_core.platforms.ios.devices import (
    allocate_ios_worker_resources,
    build_ios_worker_settings,
    load_ios_device_matrix,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path("configs/ios-device-matrix.yaml"),
    )
    parser.add_argument("--worker-count", type=int, required=True)
    return parser.parse_args(argv)


def prewarm(
    matrix_path: Path,
    worker_count: int,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Create one serial session per worker and retain its build evidence."""

    if worker_count < 1:
        raise ValueError("worker-count must be at least one")
    settings = Settings()
    matrix = load_ios_device_matrix(matrix_path)
    if worker_count > len(matrix.profiles):
        raise ValueError(
            f"worker-count {worker_count} exceeds {len(matrix.profiles)} profiles"
        )

    records: list[dict[str, Any]] = []
    for index in range(worker_count):
        worker_id = f"gw{index}"
        resources = allocate_ios_worker_resources(
            matrix,
            worker_id,
            worker_count,
            project_root,
        )
        worker_settings = build_ios_worker_settings(
            settings,
            resources.profile,
            resources,
        )
        driver = create_ios_driver(worker_settings)
        try:
            window_size = driver.get_window_size()
            assert window_size["width"] > 0
            assert window_size["height"] > 0
            record = {
                "device_id": resources.profile.device_id,
                "udid": resources.profile.udid,
                "appium_server_port": resources.appium_server_port,
                "wda_local_port": resources.wda_local_port,
                "derived_data_path": str(resources.derived_data_path),
                "window_size": window_size,
            }
            records.append(record)
        finally:
            driver.quit()

    evidence_dir = (
        project_root
        / "artifacts"
        / "ios-week20"
        / os.getenv("QA_IOS_RUN_ID", "local")
        / "prewarm"
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        path = evidence_dir / f"{record['device_id']}.json"
        path.write_text(
            json.dumps(record, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return records


def main(argv: Sequence[str] | None = None) -> int:
    """Run sequential WDA prewarm builds."""

    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    try:
        records = prewarm(args.matrix, args.worker_count, project_root)
    except Exception as exc:
        raise SystemExit(f"iOS WDA prewarm failed: {type(exc).__name__}: {exc}") from exc
    print(json.dumps(records, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
