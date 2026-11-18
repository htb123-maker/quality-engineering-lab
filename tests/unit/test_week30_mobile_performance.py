"""Week 30 mobile performance parsing and threshold contracts."""

import pytest
from qa_core.performance import (
    calculate_process_cpu_percent,
    parse_am_start_output,
    parse_battery_snapshot,
    parse_current_focus_package,
    parse_gfxinfo,
    parse_meminfo,
    parse_online_cpu_count,
    parse_proc_cpu_ticks,
    parse_ui_bounds,
    parse_wm_density,
    parse_wm_size,
    percentile,
    summarize_launches,
)


def test_parse_cold_launch_output() -> None:
    observation = parse_am_start_output(
        """
Starting: Intent { cmp=com.example.qaweek15/.MainActivity }
Status: ok
LaunchState: COLD
Activity: com.example.qaweek15/.MainActivity
TotalTime: 3904
WaitTime: 3909
Complete
"""
    )

    assert observation.status == "ok"
    assert observation.launch_state == "COLD"
    assert observation.total_time_ms == 3904
    assert observation.wait_time_ms == 3909


def test_launch_summary_uses_interpolated_percentiles() -> None:
    observations = [
        parse_am_start_output(
            "Status: ok\n"
            "LaunchState: COLD\n"
            "Activity: p/.Main\n"
            f"TotalTime: {value}\n"
            f"WaitTime: {value + 1}\n"
        )
        for value in (100, 200, 300, 400)
    ]

    summary = summarize_launches(observations)

    assert summary.count == 4
    assert summary.p50_ms == 250
    assert summary.p95_ms == pytest.approx(385)
    assert summary.min_ms == 100
    assert summary.max_ms == 400


def test_percentile_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="at least one value"):
        percentile([], 95)


def test_parse_physical_device_gfxinfo() -> None:
    metrics = parse_gfxinfo(
        """
** Graphics info for pid 13497 [com.example.qaweek15] **
Total frames rendered: 47
Janky frames: 5 (10.64%)
Janky frames (legacy): 4 (8.51%)
50th percentile: 8ms
90th percentile: 11ms
95th percentile: 30ms
99th percentile: 1700ms
Number Missed Vsync: 3
Number High input latency: 38
Number Slow UI thread: 4
Number Slow bitmap uploads: 1
Number Slow issue draw commands: 3
Number Frame deadline missed: 5
"""
    )

    assert metrics.total_frames == 47
    assert metrics.janky_frames == 5
    assert metrics.janky_frames_percent == 10.64
    assert metrics.p99_frame_ms == 1700
    assert metrics.frame_deadline_missed == 5


def test_parse_meminfo_app_summary() -> None:
    metrics = parse_meminfo(
        """
 App Summary
                       Pss(KB)                        Rss(KB)
                        ------                         ------
           Java Heap:     3888                          26884
         Native Heap:    26044                          28132
                Code:    10140                         136144
               Stack:      728                            780
            Graphics:    18076                          18076
       Private Other:     5484
              System:    25984
             Unknown:                                    8820

           TOTAL PSS:    90344            TOTAL RSS:   218836       TOTAL SWAP PSS:  9843
"""
    )

    assert metrics.total_pss_kb == 90344
    assert metrics.total_rss_kb == 218836
    assert metrics.java_heap_pss_kb == 3888
    assert metrics.native_heap_pss_kb == 26044
    assert metrics.graphics_pss_kb == 18076


def test_parse_battery_snapshot_keeps_power_context() -> None:
    snapshot = parse_battery_snapshot(
        """
Current Battery Service state:
  AC powered: false
  USB powered: true
  status: 2
  level: 45
  scale: 100
  voltage: 3231
  temperature: 270
"""
    )

    assert snapshot.level_percent == 45
    assert snapshot.status == "charging"
    assert snapshot.usb_powered is True
    assert snapshot.temperature_c == 27
    assert snapshot.voltage_mv == 3231


def test_parse_display_and_cpu_metadata() -> None:
    assert parse_wm_size("Physical size: 1440x3200") == (1440, 3200)
    assert parse_wm_density("Physical density: 560") == 560
    assert parse_online_cpu_count("0-7") == 8
    assert parse_online_cpu_count("0,2-3,6") == 4


def test_process_cpu_ticks_and_percent() -> None:
    stat_line = (
        "123 (fixture app) S 1 1 1 0 -1 0 0 0 0 0 120 30 0 0"
    )

    user_ticks, system_ticks = parse_proc_cpu_ticks(stat_line)
    cpu_percent = calculate_process_cpu_percent(
        start_ticks=0,
        end_ticks=user_ticks + system_ticks,
        elapsed_seconds=1,
    )

    assert user_ticks == 120
    assert system_ticks == 30
    assert cpu_percent == 150


def test_parse_ui_bounds_and_current_focus() -> None:
    bounds = parse_ui_bounds(
        """
<hierarchy>
  <node content-desc="fixture-counter" bounds="[48,2008][1392,2176]" />
</hierarchy>
""",
        "fixture-counter",
    )
    focus = parse_current_focus_package(
        "mCurrentFocus=Window{f307b56 u0 "
        "com.example.qaweek15/com.example.qaweek15.MainActivity}"
    )

    assert bounds.center_x == 720
    assert bounds.center_y == 2092
    assert focus == "com.example.qaweek15"


def test_parse_ui_bounds_reports_missing_element() -> None:
    with pytest.raises(ValueError, match="was not found"):
        parse_ui_bounds("<hierarchy />", "fixture-counter")
