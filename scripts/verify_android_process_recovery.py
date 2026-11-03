"""Verify Android process death and Appium session recovery."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from appium.webdriver.webdriver import WebDriver
from selenium.common.exceptions import WebDriverException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from qa_core.config.settings import Settings  # noqa: E402
from qa_core.driver.android import create_android_driver  # noqa: E402

DEFAULT_PACKAGE = "com.example.qaweek15"
DEFAULT_ACTIVITY = ".MainActivity"


@dataclass(frozen=True)
class RecoveryEvidence:
    """One process-death and recovery observation."""

    session_id: str
    package: str
    activity: str
    kill_strategy: str
    pid_before_kill: str
    pid_after_kill: str
    launch_state_after_kill: str
    old_session_probe: str
    old_session_error: str
    old_session_package: str
    old_session_activity: str
    old_app_state: str
    old_session_recovery: str
    old_recovery_package: str
    old_recovery_activity: str
    new_session_id: str
    recovered_package: str
    recovered_activity: str


def resolve_adb() -> str:
    """Resolve the project Android SDK adb or PATH fallback."""

    android_home = os.environ.get("ANDROID_HOME")
    if android_home:
        candidate = Path(android_home) / "platform-tools" / "adb.exe"
        if candidate.is_file():
            return str(candidate)
    executable = shutil.which("adb")
    if executable is None:
        raise FileNotFoundError("adb was not found in ANDROID_HOME or PATH")
    return executable


def run_adb(
    adb: str,
    serial: str,
    *arguments: str,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    """Run one bounded ADB command against the explicit device."""

    return subprocess.run(
        [adb, "-s", serial, *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def read_pid(adb: str, serial: str, package: str) -> str:
    """Return the current package PID or an empty string."""

    result = run_adb(adb, serial, "shell", "pidof", package)
    return result.stdout.strip() if result.returncode == 0 else ""


def wait_for_pid_exit(
    adb: str,
    serial: str,
    package: str,
    timeout_seconds: float = 10,
) -> str:
    """Wait until the package PID disappears and return the final observation."""

    deadline = time.monotonic() + timeout_seconds
    last_pid = read_pid(adb, serial, package)
    while last_pid and time.monotonic() < deadline:
        time.sleep(0.25)
        last_pid = read_pid(adb, serial, package)
    return last_pid


def stop_package(
    adb: str,
    serial: str,
    package: str,
    strategy: str,
    driver: WebDriver | None = None,
) -> None:
    """Stop the package with a deterministic foreground or background policy."""

    if strategy == "am-kill":
        if driver is None:
            raise ValueError("am-kill requires an active driver for HOME")
        driver.press_keycode(3)
        time.sleep(1)
        result = run_adb(adb, serial, "shell", "am", "kill", package)
    else:
        result = run_adb(adb, serial, "shell", "am", "force-stop", package)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or f"{strategy} failed")


def parse_launch_state(output: str) -> str:
    """Extract the launch state from ``am start -W`` output."""

    match = re.search(r"LaunchState:\s*([^\r\n]+)", output)
    return match.group(1).strip() if match else "unknown"


def normalized_component_activity(package: str, activity: str) -> str:
    """Normalize short Android activity names to their full component form."""

    return f"{package}{activity}" if activity.startswith(".") else activity


def start_fixture(adb: str, serial: str, component: str) -> str:
    """Start the fixture and return the observed launch state."""

    result = run_adb(
        adb,
        serial,
        "shell",
        "am",
        "start",
        "-W",
        "-n",
        component,
        timeout=60,
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode != 0:
        raise RuntimeError(output.strip() or "am start failed")
    return parse_launch_state(output)


def probe_session(driver: WebDriver, package: str) -> tuple[str, str, str, str, str]:
    """Return old-session foreground and app-state observations."""

    try:
        current_package = driver.current_package or ""
        current_activity = driver.current_activity or ""
        app_state = str(driver.query_app_state(package))
    except WebDriverException as exc:
        return (
            "failed",
            f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
            "",
            "",
            "",
        )
    except Exception as exc:  # noqa: BLE001
        return "failed", f"{type(exc).__name__}: {exc}", "", "", ""
    return "passed", "", current_package, current_activity, app_state


def recover_with_old_session(
    driver: WebDriver,
    package: str,
    component: str,
) -> tuple[str, str, str]:
    """Start the component through the surviving UiAutomator2 session."""

    try:
        driver.execute_script(
            "mobile: startActivity",
            {
                "action": "android.intent.action.MAIN",
                "component": component,
                "wait": True,
                "stop": True,
            },
        )
        time.sleep(1)
        recovered_package = driver.current_package or ""
        recovered_activity = driver.current_activity or ""
    except Exception as exc:  # noqa: BLE001
        return (
            f"failed: {type(exc).__name__}: {str(exc).splitlines()[0]}",
            "",
            "",
        )
    if recovered_package != package:
        return "unexpected package", recovered_package, recovered_activity
    return "passed", recovered_package, recovered_activity


def quit_quietly(driver: WebDriver | None) -> None:
    """Attempt session cleanup without hiding the main result."""

    if driver is None:
        return
    try:
        driver.quit()
    except Exception:  # noqa: BLE001
        pass


def build_settings(
    base: Settings,
    *,
    serial: str,
    package: str,
    activity: str,
) -> Settings:
    """Return settings targeting one explicit Android fixture."""

    return base.model_copy(
        update={
            "android_udid": serial,
            "android_device_name": "process-recovery",
            "android_app_package": package,
            "android_app_activity": activity,
        }
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--activity", default=DEFAULT_ACTIVITY)
    parser.add_argument(
        "--kill-strategy",
        choices=("force-stop", "am-kill"),
        default="force-stop",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Write evidence JSON to this path.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the process-death acceptance and return a process exit code."""

    args = parse_args(argv)
    adb = resolve_adb()
    settings = build_settings(
        Settings(),
        serial=args.serial,
        package=args.package,
        activity=args.activity,
    )
    component = f"{args.package}/{args.activity}"
    old_driver: WebDriver | None = None
    new_driver: WebDriver | None = None

    run_adb(adb, args.serial, "shell", "am", "force-stop", args.package)
    cold_launch = start_fixture(adb, args.serial, component)
    pid_before = read_pid(adb, args.serial, args.package)
    if not pid_before:
        raise RuntimeError("fixture PID was not visible after the cold launch")

    old_driver = create_android_driver(settings)
    old_session_id = old_driver.session_id

    stop_package(
        adb,
        args.serial,
        args.package,
        args.kill_strategy,
        old_driver,
    )
    pid_after = wait_for_pid_exit(adb, args.serial, args.package)
    (
        probe_status,
        probe_detail,
        old_session_package,
        old_session_activity,
        old_app_state,
    ) = probe_session(old_driver, args.package)
    (
        old_session_recovery,
        old_recovery_package,
        old_recovery_activity,
    ) = recover_with_old_session(old_driver, args.package, component)
    quit_quietly(old_driver)
    old_driver = None

    run_adb(adb, args.serial, "shell", "am", "force-stop", args.package)
    launch_state = start_fixture(adb, args.serial, component)
    new_driver = create_android_driver(settings)
    recovered_activity = new_driver.current_activity or ""
    evidence = RecoveryEvidence(
        session_id=old_session_id,
        package=args.package,
        activity=args.activity,
        kill_strategy=args.kill_strategy,
        pid_before_kill=pid_before,
        pid_after_kill=pid_after,
        launch_state_after_kill=launch_state,
        old_session_probe=probe_status,
        old_session_error=probe_detail if probe_status == "failed" else "",
        old_session_package=old_session_package,
        old_session_activity=old_session_activity,
        old_app_state=old_app_state,
        old_session_recovery=old_session_recovery,
        old_recovery_package=old_recovery_package,
        old_recovery_activity=old_recovery_activity,
        new_session_id=new_driver.session_id,
        recovered_package=new_driver.current_package or "",
        recovered_activity=recovered_activity,
    )
    quit_quietly(new_driver)
    new_driver = None

    passed = (
        not evidence.pid_after_kill
        and cold_launch != "unknown"
        and evidence.launch_state_after_kill != "unknown"
        and evidence.old_session_recovery == "passed"
        and normalized_component_activity(
            args.package,
            evidence.old_recovery_activity,
        )
        == normalized_component_activity(args.package, args.activity)
        and evidence.recovered_package == args.package
        and normalized_component_activity(args.package, recovered_activity)
        == normalized_component_activity(args.package, args.activity)
    )
    payload: dict[str, Any] = {
        "passed": passed,
        "cold_launch": cold_launch,
        **asdict(evidence),
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
