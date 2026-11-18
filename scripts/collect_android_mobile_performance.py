"""Collect Android launch, rendering, memory, CPU, and battery evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from qa_core.performance import (  # noqa: E402
    BatterySnapshot,
    LaunchObservation,
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
    summarize_launches,
)

DEFAULT_PACKAGE = "com.example.qaweek15"
DEFAULT_ACTIVITY = ".MainActivity"
DEFAULT_COLD_RUNS = 10
DEFAULT_WARM_RUNS = 10
DEFAULT_TAPS = 40


@dataclass(frozen=True)
class Thresholds:
    """Acceptance thresholds for one Android performance run."""

    cold_p95_ms: float = 5_000.0
    warm_p95_ms: float = 2_000.0
    background_resume_ms: int = 1_500
    minimum_frames: int = 30
    maximum_jank_percent: float = 5.0
    minimum_memory_pss_kb: int = 1_024


class AdbClient:
    """Small, explicit ADB wrapper for one physical device."""

    def __init__(self, adb: str, serial: str) -> None:
        self.adb = adb
        self.serial = serial

    def run(
        self,
        *arguments: str,
        timeout_seconds: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.adb, "-s", self.serial, *arguments],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )

    def shell(self, *arguments: str, timeout_seconds: float = 60) -> str:
        result = self.run(
            "shell",
            *arguments,
            timeout_seconds=timeout_seconds,
        )
        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"adb shell {' '.join(arguments)} failed with "
                f"exit code {result.returncode}: {output}"
            )
        return output

    def shell_file(self, path: str, timeout_seconds: float = 20) -> str:
        return self.shell("cat", path, timeout_seconds=timeout_seconds)


def resolve_adb() -> str:
    """Resolve ADB from ``ANDROID_HOME`` or ``PATH``."""

    android_home = os.environ.get("ANDROID_HOME")
    if android_home:
        candidate = Path(android_home) / "platform-tools" / "adb.exe"
        if candidate.is_file():
            return str(candidate)
    executable = shutil.which("adb")
    if executable is None:
        raise FileNotFoundError("adb was not found in ANDROID_HOME or PATH")
    return executable


def normalized_component(package: str, activity: str) -> str:
    """Return the explicit package/activity component."""

    return f"{package}/{activity}"


def read_pid(adb: AdbClient, package: str) -> str:
    """Return the first PID for the target package."""

    output = adb.shell("pidof", package).strip()
    if not output:
        raise RuntimeError(f"process for {package} was not running")
    return output.split()[0]


def read_property(adb: AdbClient, property_name: str) -> str:
    """Read one Android system property."""

    return adb.shell("getprop", property_name).strip()


def start_component(
    adb: AdbClient,
    component: str,
    *,
    cold: bool,
) -> LaunchObservation:
    """Start an Activity and parse its ``am start -W`` timing."""

    arguments = ["am", "start", "-W"]
    if cold:
        arguments.append("-S")
    arguments.extend(["-n", component])
    return parse_am_start_output(adb.shell(*arguments, timeout_seconds=90))


def wake_device(adb: AdbClient) -> None:
    """Wake a test device without toggling an already-awake display."""

    adb.shell("input", "keyevent", "224")


def move_to_background(adb: AdbClient, package: str) -> str:
    """Press HOME and wait until the target package is no longer focused."""

    last_focus = ""
    for _ in range(3):
        adb.shell("input", "keyevent", "3")
        time.sleep(0.6)
        last_focus = parse_current_focus_package(adb.shell("dumpsys", "window"))
        if last_focus != package:
            return last_focus
    raise RuntimeError(
        f"{package} remained focused after three HOME attempts; last focus={last_focus}"
    )


def collect_launches(
    adb: AdbClient,
    *,
    component: str,
    package: str,
    cold_runs: int,
    warm_runs: int,
) -> dict[str, Any]:
    """Collect cold and warm Activity launch samples."""

    cold: list[LaunchObservation] = []
    warm: list[LaunchObservation] = []

    for _ in range(cold_runs):
        wake_device(adb)
        adb.shell("am", "force-stop", package)
        time.sleep(0.3)
        cold.append(start_component(adb, component, cold=True))
        time.sleep(0.7)

    for _ in range(warm_runs):
        wake_device(adb)
        move_to_background(adb, package)
        warm.append(start_component(adb, component, cold=False))
        time.sleep(0.5)

    return {
        "cold": {
            "observations": [item.model_dump(mode="json") for item in cold],
            "summary": summarize_launches(cold).model_dump(mode="json"),
        },
        "warm": {
            "observations": [item.model_dump(mode="json") for item in warm],
            "summary": summarize_launches(warm).model_dump(mode="json"),
        },
    }


def collect_background_recovery(
    adb: AdbClient,
    *,
    component: str,
    package: str,
) -> dict[str, Any]:
    """Measure a HOME-to-relaunch cycle and verify target focus."""

    wake_device(adb)
    adb.shell("am", "force-stop", package)
    initial = start_component(adb, component, cold=True)
    focus_after_home = move_to_background(adb, package)
    resumed = start_component(adb, component, cold=False)
    focus_after_resume = parse_current_focus_package(
        adb.shell("dumpsys", "window")
    )
    return {
        "initial_launch": initial.model_dump(mode="json"),
        "resume_launch": resumed.model_dump(mode="json"),
        "focus_after_home": focus_after_home,
        "focus_after_resume": focus_after_resume,
        "passed": (
            focus_after_home != package
            and focus_after_resume == package
            and resumed.total_time_ms <= 1_500
        ),
    }


def collect_rendering_and_resources(
    adb: AdbClient,
    *,
    component: str,
    package: str,
    taps: int,
) -> dict[str, Any]:
    """Generate real taps and capture jank, memory, and CPU evidence."""

    wake_device(adb)
    adb.shell("am", "force-stop", package)
    start_component(adb, component, cold=True)
    time.sleep(1.0)
    ui_path = "/sdcard/qa-mobile-performance-window.xml"
    adb.shell("uiautomator", "dump", ui_path, timeout_seconds=30)
    ui_xml = adb.shell_file(ui_path)
    adb.shell("rm", ui_path)
    counter_bounds = parse_ui_bounds(ui_xml, "fixture-counter")

    adb.shell("dumpsys", "gfxinfo", package, "reset")
    app_pid = read_pid(adb, package)
    cpu_stat_path = f"/proc/{app_pid}/stat"
    start_ticks = sum(parse_proc_cpu_ticks(adb.shell_file(cpu_stat_path)))
    started_at = time.monotonic()
    for _ in range(taps):
        adb.shell(
            "input",
            "tap",
            str(counter_bounds.center_x),
            str(counter_bounds.center_y),
        )
        time.sleep(0.12)
    elapsed_seconds = max(time.monotonic() - started_at, 0.001)
    end_ticks = sum(parse_proc_cpu_ticks(adb.shell_file(cpu_stat_path)))
    cpu_percent = calculate_process_cpu_percent(
        start_ticks=start_ticks,
        end_ticks=end_ticks,
        elapsed_seconds=elapsed_seconds,
    )
    cpu_count = parse_online_cpu_count(
        adb.shell_file("/sys/devices/system/cpu/online")
    )

    time.sleep(1.0)
    graphics = parse_gfxinfo(adb.shell("dumpsys", "gfxinfo", package))
    memory = parse_meminfo(adb.shell("dumpsys", "meminfo", package))
    return {
        "interaction": {
            "action": "tap fixture-counter",
            "taps": taps,
            "target": {
                "x": counter_bounds.center_x,
                "y": counter_bounds.center_y,
                "bounds": counter_bounds.model_dump(mode="json"),
            },
            "elapsed_seconds": round(elapsed_seconds, 3),
        },
        "graphics": graphics.model_dump(mode="json"),
        "memory": memory.model_dump(mode="json"),
        "cpu": {
            "process_percent": round(cpu_percent, 3),
            "normalized_device_percent": round(cpu_percent / cpu_count, 3),
            "online_cpu_count": cpu_count,
            "sample_seconds": round(elapsed_seconds, 3),
            "source": cpu_stat_path,
        },
    }


def collect_battery(adb: AdbClient) -> BatterySnapshot:
    """Read one battery snapshot."""

    return parse_battery_snapshot(adb.shell("dumpsys", "battery"))


def build_checks(
    *,
    launches: dict[str, Any],
    background: dict[str, Any],
    rendering: dict[str, Any],
    memory_pss_kb: int,
    thresholds: Thresholds,
) -> list[dict[str, Any]]:
    """Build all machine-checkable mobile observations."""

    cold_p95 = float(launches["cold"]["summary"]["p95_ms"])
    warm_p95 = float(launches["warm"]["summary"]["p95_ms"])
    resume_ms = int(background["resume_launch"]["total_time_ms"])
    frames = int(rendering["graphics"]["total_frames"])
    jank_percent = float(rendering["graphics"]["janky_frames_percent"])
    checks = [
        {
            "name": "cold_launch_p95",
            "actual": cold_p95,
            "operator": "lte",
            "threshold": thresholds.cold_p95_ms,
            "passed": cold_p95 <= thresholds.cold_p95_ms,
        },
        {
            "name": "warm_launch_p95",
            "actual": warm_p95,
            "operator": "lte",
            "threshold": thresholds.warm_p95_ms,
            "passed": warm_p95 <= thresholds.warm_p95_ms,
        },
        {
            "name": "background_resume",
            "actual": resume_ms,
            "operator": "lte",
            "threshold": thresholds.background_resume_ms,
            "passed": (
                bool(background["passed"])
                and resume_ms <= thresholds.background_resume_ms
            ),
        },
        {
            "name": "rendered_frames",
            "actual": frames,
            "operator": "gte",
            "threshold": thresholds.minimum_frames,
            "passed": frames >= thresholds.minimum_frames,
        },
        {
            "name": "janky_frames",
            "actual": jank_percent,
            "operator": "lte",
            "threshold": thresholds.maximum_jank_percent,
            "passed": jank_percent <= thresholds.maximum_jank_percent,
        },
        {
            "name": "memory_pss",
            "actual": memory_pss_kb,
            "operator": "gte",
            "threshold": thresholds.minimum_memory_pss_kb,
            "passed": memory_pss_kb >= thresholds.minimum_memory_pss_kb,
        },
    ]
    return checks


def collect_environment(
    adb: AdbClient,
    *,
    package: str,
    activity: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Collect device and app metadata."""

    width, height = parse_wm_size(adb.shell("wm", "size"))
    density = parse_wm_density(adb.shell("wm", "density"))
    package_path = adb.shell("pm", "path", package).strip()
    package_dump = adb.shell("dumpsys", "package", package)
    version_name = "unknown"
    version_code = "unknown"
    for line in package_dump.splitlines():
        stripped = line.strip()
        if stripped.startswith("versionName="):
            version_name = stripped.split("=", 1)[1]
        elif stripped.startswith("versionCode="):
            version_code = stripped.split("=", 1)[1].split()[0]

    device = {
        "serial": adb.serial,
        "manufacturer": read_property(adb, "ro.product.manufacturer"),
        "model": read_property(adb, "ro.product.model"),
        "android_release": read_property(adb, "ro.build.version.release"),
        "android_sdk": read_property(adb, "ro.build.version.sdk"),
        "build_fingerprint": read_property(adb, "ro.build.fingerprint"),
        "display_width_px": width,
        "display_height_px": height,
        "display_density_dpi": density,
    }
    app = {
        "package": package,
        "activity": activity,
        "version_name": version_name,
        "version_code": version_code,
        "installed_path": package_path.removeprefix("package:"),
    }
    return device, app


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse collector options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--activity", default=DEFAULT_ACTIVITY)
    parser.add_argument("--cold-runs", type=int, default=DEFAULT_COLD_RUNS)
    parser.add_argument("--warm-runs", type=int, default=DEFAULT_WARM_RUNS)
    parser.add_argument("--taps", type=int, default=DEFAULT_TAPS)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/performance/week30/android/mobile-performance.json"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Android mobile performance acceptance path."""

    args = parse_args(argv)
    if args.cold_runs < 1 or args.warm_runs < 1 or args.taps < 1:
        raise ValueError("cold runs, warm runs, and taps must all be positive")

    adb = AdbClient(resolve_adb(), args.serial)
    state = adb.run("get-state", timeout_seconds=10).stdout.strip()
    if state != "device":
        raise RuntimeError(
            f"Android device {args.serial} is not ready; expected 'device', got {state!r}"
        )

    thresholds = Thresholds()
    component = normalized_component(args.package, args.activity)
    battery_start = collect_battery(adb)
    launches = collect_launches(
        adb,
        component=component,
        package=args.package,
        cold_runs=args.cold_runs,
        warm_runs=args.warm_runs,
    )
    background = collect_background_recovery(
        adb,
        component=component,
        package=args.package,
    )
    resources = collect_rendering_and_resources(
        adb,
        component=component,
        package=args.package,
        taps=args.taps,
    )
    battery_end = collect_battery(adb)
    device, app = collect_environment(
        adb,
        package=args.package,
        activity=args.activity,
    )
    checks = build_checks(
        launches=launches,
        background=background,
        rendering=resources,
        memory_pss_kb=int(resources["memory"]["total_pss_kb"]),
        thresholds=thresholds,
    )
    status = "PASS" if all(check["passed"] for check in checks) else "FAILED"

    payload: dict[str, Any] = {
        "schema_version": 1,
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "platform": "android",
        "device": device,
        "app": app,
        "thresholds": asdict(thresholds),
        "launches": launches,
        "background_recovery": background,
        "interaction": resources["interaction"],
        "rendering": resources["graphics"],
        "memory": resources["memory"],
        "cpu": resources["cpu"],
        "battery": {
            "start": battery_start.model_dump(mode="json"),
            "end": battery_end.model_dump(mode="json"),
            "energy_delta_interpretable": (
                not battery_start.usb_powered
                and not battery_start.ac_powered
                and battery_start.status == "discharging"
            ),
        },
        "weak_network": {
            "status": "NOT RUN",
            "reason": (
                "The current Android fixture has no network-dependent journey. "
                "Disabling connectivity would not test app behavior."
            ),
        },
        "ios": {
            "status": "DEFERRED",
            "reason": (
                "No local macOS runner or iOS device is attached to this Windows host."
            ),
        },
        "checks": checks,
        "limitations": [
            "am start -W reports ActivityManager launch timing, not frame-level startup.",
            "jank is measured after launch and reset, using 40 real counter taps.",
            "A single Xiaomi physical device does not represent the full Android matrix.",
            "The fixture has no network journey, so weak-network behavior is not verified.",
            "Battery snapshot values are not a controlled energy measurement.",
            "The fixture is USB powered, so battery percentage is not an energy metric.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    adb.shell("am", "force-stop", args.package)
    print(json.dumps({"status": status, "output": str(args.output)}, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
