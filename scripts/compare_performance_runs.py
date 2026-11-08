"""Compare Week 26 Baseline and Load summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from qa_core.performance import (
    ObservedPerformance,
    compare_observations,
    render_html_report,
    summarize_resource_csvs,
)


def main() -> int:
    """Write comparison.json and report.html from two profile summaries."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--load-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    baseline_summary = _load_json(args.baseline_dir / "summary.json")
    load_summary = _load_json(args.load_dir / "summary.json")
    baseline_observed = ObservedPerformance.model_validate(baseline_summary["observed"])
    load_observed = ObservedPerformance.model_validate(load_summary["observed"])
    baseline_resources = summarize_resource_csvs(
        sorted(args.baseline_dir.glob("run-*/resources.csv"))
    )
    load_resources = summarize_resource_csvs(sorted(args.load_dir.glob("run-*/resources.csv")))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "baseline_profile": baseline_summary["profile_name"],
        "load_profile": load_summary["profile_name"],
        "baseline_slo_passed": baseline_summary["slo_passed"],
        "load_slo_passed": load_summary["slo_passed"],
        "metrics": compare_observations(baseline_observed, load_observed),
        "resources": {
            "baseline": baseline_resources,
            "load": load_resources,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "comparison.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "report.html").write_text(
        render_html_report(payload),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _load_json(path: Path) -> dict[str, Any]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
