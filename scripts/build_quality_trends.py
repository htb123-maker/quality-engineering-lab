"""Build JSON and HTML quality trends from CI evidence artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa_core.reporting import (
    TrendHistory,
    append_history,
    build_trend_point,
    discover_checks,
    load_history,
    render_trend_html,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--history", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--html-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    history = load_history(args.history) if args.history else TrendHistory()
    checks = discover_checks(args.artifacts_root)
    point = build_trend_point(
        run_id=args.run_id,
        commit=args.commit,
        checks=checks,
    )
    history = append_history(history, point)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.html_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(history.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    args.html_output.write_text(render_trend_html(history), encoding="utf-8")
    print(f"quality trend: {args.json_output}")
    print(f"checks: {len(checks)}, overall: {point.overall}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
