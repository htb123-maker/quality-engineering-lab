"""Summarize repeated performance runs and compare Baseline with Load."""

from __future__ import annotations

import csv
import hashlib
import html
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from qa_core.performance.models import ObservedPerformance

_RESOURCE_METRICS = (
    "cpu_percent",
    "memory_usage_bytes",
    "memory_limit_bytes",
    "network_io_bytes",
    "block_io_bytes",
)


def profile_sha256(path: Path) -> str:
    """Return the stable digest recorded with every result manifest."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_observations(
    observations: Sequence[ObservedPerformance],
) -> ObservedPerformance:
    """Return median metrics across repeated measured runs."""

    if not observations:
        raise ValueError("at least one observation is required")
    return ObservedPerformance(
        total_requests=int(statistics.median(item.total_requests for item in observations)),
        error_rate=statistics.median(item.error_rate for item in observations),
        p50_response_time_ms=statistics.median(item.p50_response_time_ms for item in observations),
        p95_response_time_ms=statistics.median(item.p95_response_time_ms for item in observations),
        p99_response_time_ms=statistics.median(item.p99_response_time_ms for item in observations),
        requests_per_second=statistics.median(item.requests_per_second for item in observations),
        duration_seconds=statistics.median(item.duration_seconds for item in observations),
    )


def compare_observations(
    baseline: ObservedPerformance,
    load: ObservedPerformance,
) -> dict[str, dict[str, float | int | None]]:
    """Return absolute and percent changes for every comparable metric."""

    baseline_values = baseline.model_dump()
    load_values = load.model_dump()
    comparison: dict[str, dict[str, float | int | None]] = {}
    for metric, baseline_value in baseline_values.items():
        load_value = load_values[metric]
        absolute = load_value - baseline_value
        percent = None if baseline_value == 0 else (absolute / baseline_value) * 100
        comparison[metric] = {
            "baseline": baseline_value,
            "load": load_value,
            "absolute_delta": absolute,
            "percent_delta": percent,
        }
    return comparison


def summarize_resource_csvs(
    paths: Sequence[Path],
) -> dict[str, dict[str, float]]:
    """Return median resource metrics grouped by Compose service."""

    grouped: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {metric: [] for metric in _RESOURCE_METRICS}
    )
    for path in paths:
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as file_handle:
            for row in csv.DictReader(file_handle):
                service = row.get("service", "")
                if not service:
                    continue
                for metric in _RESOURCE_METRICS:
                    raw = row.get(metric)
                    if raw is None or raw == "":
                        continue
                    grouped[service][metric].append(float(raw))
    return {
        service: {metric: statistics.median(values) for metric, values in metrics.items() if values}
        for service, metrics in grouped.items()
    }


def render_html_report(payload: Mapping[str, Any]) -> str:
    """Render a small self-contained comparison report."""

    baseline = str(payload.get("baseline_profile", "baseline"))
    load = str(payload.get("load_profile", "load"))
    comparison = payload.get("metrics", {})
    rows: list[str] = []
    if isinstance(comparison, Mapping):
        for metric, values in comparison.items():
            if not isinstance(values, Mapping):
                continue
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(metric))}</td>"
                f"<td>{_format_value(values.get('baseline'))}</td>"
                f"<td>{_format_value(values.get('load'))}</td>"
                f"<td>{_format_value(values.get('percent_delta'))}</td>"
                "</tr>"
            )
    resources = payload.get("resources", {})
    resource_rows: list[str] = []
    if isinstance(resources, Mapping):
        for service, values in resources.items():
            if not isinstance(values, Mapping):
                continue
            resource_rows.append(
                "<tr>"
                f"<td>{html.escape(str(service))}</td>"
                f"<td>{_format_value(values.get('cpu_percent'))}</td>"
                f"<td>{_format_value(values.get('memory_usage_bytes'))}</td>"
                f"<td>{_format_value(values.get('network_io_bytes'))}</td>"
                f"<td>{_format_value(values.get('block_io_bytes'))}</td>"
                "</tr>"
            )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Week 26 performance comparison</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; color: #1f2937; }}
    table {{ border-collapse: collapse; margin-bottom: 2rem; width: 100%; }}
    th, td {{ border: 1px solid #d1d5db; padding: 0.5rem; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ background: #f3f4f6; }}
    code {{ background: #f3f4f6; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>Week 26 Baseline / Load comparison</h1>
  <p>Baseline <code>{html.escape(baseline)}</code> versus load
     <code>{html.escape(load)}</code>.</p>
  <p>Percent delta is relative to the baseline. Positive latency or error-rate
     deltas indicate regression.</p>
  <h2>Metrics</h2>
  <table>
    <thead>
      <tr><th>Metric</th><th>Baseline</th><th>Load</th><th>Delta %</th></tr>
    </thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  <h2>Median resource samples</h2>
  <table>
    <thead>
      <tr><th>Service</th><th>CPU %</th><th>Memory bytes</th>
          <th>Network bytes</th><th>Block IO bytes</th></tr>
    </thead>
    <tbody>{"".join(resource_rows)}</tbody>
  </table>
</body>
</html>
"""


def _format_value(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.3f}"
    return html.escape(str(value))
