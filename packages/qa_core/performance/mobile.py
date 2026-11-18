"""Parsers and summaries for Android mobile performance evidence."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field


class LaunchObservation(BaseModel):
    """One parsed ``am start -W`` observation."""

    model_config = ConfigDict(frozen=True)

    status: str
    launch_state: str
    activity: str
    total_time_ms: int = Field(ge=0)
    wait_time_ms: int = Field(ge=0)


class LaunchSummary(BaseModel):
    """Latency summary for repeated launch observations."""

    model_config = ConfigDict(frozen=True)

    count: int = Field(ge=1)
    p50_ms: float = Field(ge=0.0)
    p95_ms: float = Field(ge=0.0)
    min_ms: int = Field(ge=0)
    max_ms: int = Field(ge=0)


class GraphicsMetrics(BaseModel):
    """Relevant fields from ``dumpsys gfxinfo <package>``."""

    model_config = ConfigDict(frozen=True)

    total_frames: int = Field(ge=0)
    janky_frames: int = Field(ge=0)
    janky_frames_percent: float = Field(ge=0.0)
    janky_frames_legacy: int = Field(ge=0)
    janky_frames_legacy_percent: float = Field(ge=0.0)
    p50_frame_ms: float = Field(ge=0.0)
    p90_frame_ms: float = Field(ge=0.0)
    p95_frame_ms: float = Field(ge=0.0)
    p99_frame_ms: float = Field(ge=0.0)
    missed_vsync: int = Field(ge=0)
    high_input_latency: int = Field(ge=0)
    slow_ui_thread: int = Field(ge=0)
    slow_bitmap_uploads: int = Field(ge=0)
    slow_issue_draw_commands: int = Field(ge=0)
    frame_deadline_missed: int = Field(ge=0)


class MemoryMetrics(BaseModel):
    """PSS and RSS values parsed from ``dumpsys meminfo <package>``."""

    model_config = ConfigDict(frozen=True)

    total_pss_kb: int = Field(ge=0)
    total_rss_kb: int = Field(ge=0)
    java_heap_pss_kb: int = Field(ge=0)
    native_heap_pss_kb: int = Field(ge=0)
    graphics_pss_kb: int = Field(ge=0)


class BatterySnapshot(BaseModel):
    """One battery snapshot from ``dumpsys battery``."""

    model_config = ConfigDict(frozen=True)

    level_percent: int = Field(ge=0, le=100)
    status: str
    usb_powered: bool
    ac_powered: bool
    temperature_c: float
    voltage_mv: int = Field(ge=0)


class UiBounds(BaseModel):
    """Screen bounds for one UI element."""

    model_config = ConfigDict(frozen=True)

    left: int = Field(ge=0)
    top: int = Field(ge=0)
    right: int = Field(ge=0)
    bottom: int = Field(ge=0)

    @property
    def center_x(self) -> int:
        return self.left + (self.right - self.left) // 2

    @property
    def center_y(self) -> int:
        return self.top + (self.bottom - self.top) // 2


_BATTERY_STATUS = {
    "1": "unknown",
    "2": "charging",
    "3": "discharging",
    "4": "not-charging",
    "5": "full",
}


def _required_match(pattern: str, text: str, label: str) -> re.Match[str]:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise ValueError(f"{label} was not found in command output")
    return match


def _required_int(pattern: str, text: str, label: str) -> int:
    return int(_required_match(pattern, text, label).group(1))


def _required_float(pattern: str, text: str, label: str) -> float:
    return float(_required_match(pattern, text, label).group(1))


def parse_am_start_output(output: str) -> LaunchObservation:
    """Parse the stable fields printed by ``am start -W``."""

    return LaunchObservation(
        status=_required_match(r"^Status:\s*(.+)$", output, "Status").group(1).strip(),
        launch_state=_required_match(
            r"^LaunchState:\s*(.+)$",
            output,
            "LaunchState",
        )
        .group(1)
        .strip(),
        activity=_required_match(r"^Activity:\s*(.+)$", output, "Activity")
        .group(1)
        .strip(),
        total_time_ms=_required_int(
            r"^TotalTime:\s*(\d+)\s*$",
            output,
            "TotalTime",
        ),
        wait_time_ms=_required_int(r"^WaitTime:\s*(\d+)\s*$", output, "WaitTime"),
    )


def parse_gfxinfo(output: str) -> GraphicsMetrics:
    """Parse jank and frame timing fields from one package graphics snapshot."""

    return GraphicsMetrics(
        total_frames=_required_int(
            r"^Total frames rendered:\s*(\d+)\s*$",
            output,
            "Total frames rendered",
        ),
        janky_frames=_required_int(
            r"^Janky frames:\s*(\d+)\s",
            output,
            "Janky frames",
        ),
        janky_frames_percent=_required_float(
            r"^Janky frames:\s*\d+\s*\(([\d.]+)%\)",
            output,
            "Janky frames percent",
        ),
        janky_frames_legacy=_required_int(
            r"^Janky frames \(legacy\):\s*(\d+)\s",
            output,
            "Janky frames legacy",
        ),
        janky_frames_legacy_percent=_required_float(
            r"^Janky frames \(legacy\):\s*\d+\s*\(([\d.]+)%\)",
            output,
            "Janky frames legacy percent",
        ),
        p50_frame_ms=_required_float(
            r"^50th percentile:\s*([\d.]+)ms",
            output,
            "50th percentile",
        ),
        p90_frame_ms=_required_float(
            r"^90th percentile:\s*([\d.]+)ms",
            output,
            "90th percentile",
        ),
        p95_frame_ms=_required_float(
            r"^95th percentile:\s*([\d.]+)ms",
            output,
            "95th percentile",
        ),
        p99_frame_ms=_required_float(
            r"^99th percentile:\s*([\d.]+)ms",
            output,
            "99th percentile",
        ),
        missed_vsync=_required_int(
            r"^Number Missed Vsync:\s*(\d+)\s*$",
            output,
            "Number Missed Vsync",
        ),
        high_input_latency=_required_int(
            r"^Number High input latency:\s*(\d+)\s*$",
            output,
            "Number High input latency",
        ),
        slow_ui_thread=_required_int(
            r"^Number Slow UI thread:\s*(\d+)\s*$",
            output,
            "Number Slow UI thread",
        ),
        slow_bitmap_uploads=_required_int(
            r"^Number Slow bitmap uploads:\s*(\d+)\s*$",
            output,
            "Number Slow bitmap uploads",
        ),
        slow_issue_draw_commands=_required_int(
            r"^Number Slow issue draw commands:\s*(\d+)\s*$",
            output,
            "Number Slow issue draw commands",
        ),
        frame_deadline_missed=_required_int(
            r"^Number Frame deadline missed:\s*(\d+)\s*$",
            output,
            "Number Frame deadline missed",
        ),
    )


def parse_meminfo(output: str) -> MemoryMetrics:
    """Parse total and category memory values from ``dumpsys meminfo``."""

    return MemoryMetrics(
        total_pss_kb=_required_int(r"^\s*TOTAL PSS:\s*(\d+)", output, "TOTAL PSS"),
        total_rss_kb=_required_int(r"TOTAL RSS:\s*(\d+)", output, "TOTAL RSS"),
        java_heap_pss_kb=_required_int(r"^\s*Java Heap:\s*(\d+)", output, "Java Heap"),
        native_heap_pss_kb=_required_int(
            r"^\s*Native Heap:\s*(\d+)",
            output,
            "Native Heap",
        ),
        graphics_pss_kb=_required_int(r"^\s*Graphics:\s*(\d+)", output, "Graphics"),
    )


def parse_battery_snapshot(output: str) -> BatterySnapshot:
    """Parse the battery fields needed for a short mobile observation."""

    fields: dict[str, str] = {}
    for line in output.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().lower()] = value.strip()

    level = int(fields["level"])
    scale = int(fields.get("scale", "100"))
    status_code = fields.get("status", "1")
    return BatterySnapshot(
        level_percent=round(level * 100 / scale),
        status=_BATTERY_STATUS.get(status_code, f"unknown-{status_code}"),
        usb_powered=fields.get("usb powered", "false").lower() == "true",
        ac_powered=fields.get("ac powered", "false").lower() == "true",
        temperature_c=float(fields.get("temperature", "0")) / 10,
        voltage_mv=int(fields.get("voltage", "0")),
    )


def parse_wm_size(output: str) -> tuple[int, int]:
    """Return the physical display width and height in pixels."""

    match = _required_match(r"Physical size:\s*(\d+)x(\d+)", output, "Physical size")
    return int(match.group(1)), int(match.group(2))


def parse_wm_density(output: str) -> int:
    """Return the physical display density in dpi."""

    return _required_int(r"Physical density:\s*(\d+)", output, "Physical density")


def parse_online_cpu_count(output: str) -> int:
    """Count CPUs from the Linux ``/sys/devices/system/cpu/online`` syntax."""

    count = 0
    for part in output.strip().split(","):
        if "-" in part:
            start, end = part.split("-", 1)
            count += int(end) - int(start) + 1
        elif part:
            count += 1
    if count <= 0:
        raise ValueError("online CPU list did not contain any CPUs")
    return count


def parse_proc_cpu_ticks(stat_line: str) -> tuple[int, int]:
    """Return user and system CPU ticks from one ``/proc/<pid>/stat`` line."""

    closing_parenthesis = stat_line.rfind(")")
    if closing_parenthesis < 0:
        raise ValueError("process stat line does not contain a command boundary")
    fields = stat_line[closing_parenthesis + 1 :].split()
    if len(fields) < 13:
        raise ValueError("process stat line did not contain CPU tick fields")
    return int(fields[11]), int(fields[12])


def calculate_process_cpu_percent(
    *,
    start_ticks: int,
    end_ticks: int,
    elapsed_seconds: float,
    clock_ticks_per_second: int = 100,
) -> float:
    """Return process CPU usage in the same per-core units as ``top``."""

    if elapsed_seconds <= 0:
        raise ValueError("elapsed_seconds must be positive")
    if end_ticks < start_ticks:
        raise ValueError("CPU ticks moved backwards")
    return (
        (end_ticks - start_ticks)
        / clock_ticks_per_second
        / elapsed_seconds
        * 100
    )


def parse_ui_bounds(xml_text: str, content_description: str) -> UiBounds:
    """Find one accessible element and return its screen bounds."""

    root = ElementTree.fromstring(xml_text)
    for node in root.iter("node"):
        if node.attrib.get("content-desc") != content_description:
            continue
        match = re.fullmatch(
            r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",
            node.attrib.get("bounds", ""),
        )
        if match is None:
            raise ValueError(
                f"element {content_description!r} has invalid bounds"
            )
        return UiBounds(
            left=int(match.group(1)),
            top=int(match.group(2)),
            right=int(match.group(3)),
            bottom=int(match.group(4)),
        )
    raise ValueError(f"element {content_description!r} was not found")


def parse_current_focus_package(output: str) -> str:
    """Return the package from the ``mCurrentFocus`` window dump."""

    match = _required_match(
        r"mCurrentFocus=.*?\s([A-Za-z0-9_.]+)/[A-Za-z0-9_.$]+",
        output,
        "mCurrentFocus",
    )
    return match.group(1)


def percentile(values: Sequence[float], percentage: float) -> float:
    """Return a linearly interpolated percentile for a non-empty sample."""

    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= percentage <= 100:
        raise ValueError("percentage must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentage / 100
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = rank - lower_index
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction


def summarize_launches(
    observations: Sequence[LaunchObservation],
) -> LaunchSummary:
    """Summarize repeated launch total times."""

    if not observations:
        raise ValueError("at least one launch observation is required")
    values = [float(item.total_time_ms) for item in observations]
    return LaunchSummary(
        count=len(values),
        p50_ms=percentile(values, 50),
        p95_ms=percentile(values, 95),
        min_ms=int(min(values)),
        max_ms=int(max(values)),
    )
