"""Verify Appium behavior across a wireless ADB disconnect and reconnect."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from appium.webdriver.webdriver import WebDriver

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "packages"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for module_path in (PACKAGES_DIR, SCRIPTS_DIR):
    if str(module_path) not in sys.path:
        sys.path.insert(0, str(module_path))

from qa_core.config.settings import Settings  # noqa: E402
from qa_core.driver.android import create_android_driver  # noqa: E402
from verify_android_process_recovery import (  # noqa: E402
    DEFAULT_ACTIVITY,
    DEFAULT_PACKAGE,
    build_settings,
    normalized_component_activity,
    quit_quietly,
    resolve_adb,
    run_adb,
    start_fixture,
)


@dataclass(frozen=True)
class TransportEvidence:
    """One ADB outage and Appium-session recovery observation."""

    serial: str
    package: str
    activity: str
    session_id: str
    pid_before_disconnect: str
    adb_state_during_outage: str
    old_session_during_outage: str
    old_session_error: str
    adb_state_after_reconnect: str
    old_session_after_reconnect: str
    old_package_after_reconnect: str
    old_activity_after_reconnect: str
    new_session_id: str
    recovered_package: str
    recovered_activity: str


def wait_for_adb_state(
    adb: str,
    serial: str,
    expected: str,
    timeout_seconds: float = 30,
) -> str:
    """Wait for an exact ADB state and return the last observed value."""

    deadline = time.monotonic() + timeout_seconds
    state = ""
    while time.monotonic() < deadline:
        result = run_adb(adb, serial, "get-state")
        state = result.stdout.strip()
        if result.returncode == 0 and state == expected:
            return state
        time.sleep(0.5)
    return state


def run_adb_server(
    adb: str,
    *arguments: str,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    """Run a server-level ADB command such as connect or disconnect."""

    return subprocess.run(
        [adb, *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def probe_session(driver: WebDriver) -> tuple[str, str, str, str]:
    """Return session status, package, activity, and failure detail."""

    try:
        package = driver.current_package or ""
        activity = driver.current_activity or ""
    except Exception as exc:  # noqa: BLE001
        return "failed", "", "", f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
    return "passed", package, activity, ""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--activity", default=DEFAULT_ACTIVITY)
    parser.add_argument("--reconnect-timeout", type=float, default=30)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the wireless ADB outage acceptance and return an exit code."""

    args = parse_args(argv)
    adb = resolve_adb()
    settings = build_settings(
        Settings(),
        serial=args.serial,
        package=args.package,
        activity=args.activity,
    ).model_copy(update={"android_adb_exec_timeout_ms": 10_000})
    component = f"{args.package}/{args.activity}"
    old_driver: WebDriver | None = None
    new_driver: WebDriver | None = None
    reconnect_attempted = False

    try:
        run_adb(adb, args.serial, "shell", "am", "force-stop", args.package)
        start_fixture(adb, args.serial, component)
        pid_result = run_adb(adb, args.serial, "shell", "pidof", args.package)
        pid_before = pid_result.stdout.strip()
        if not pid_before:
            raise RuntimeError("fixture PID was not visible before disconnect")

        old_driver = create_android_driver(settings)
        old_session_id = old_driver.session_id

        disconnect = run_adb_server(adb, "disconnect", args.serial)
        if disconnect.returncode != 0:
            raise RuntimeError(
                (disconnect.stderr or disconnect.stdout).strip()
                or "adb disconnect failed"
            )
        reconnect_attempted = True
        time.sleep(2)
        outage = run_adb(adb, args.serial, "get-state")
        adb_state_during_outage = outage.stdout.strip() or outage.stderr.strip()
        during_status, _, _, during_error = probe_session(old_driver)

        reconnect = run_adb_server(adb, "connect", args.serial)
        if reconnect.returncode != 0:
            raise RuntimeError(
                (reconnect.stderr or reconnect.stdout).strip()
                or "adb reconnect failed"
            )
        adb_state_after_reconnect = wait_for_adb_state(
            adb,
            args.serial,
            "device",
            timeout_seconds=args.reconnect_timeout,
        )
        (
            after_status,
            old_package,
            old_activity,
            after_error,
        ) = probe_session(old_driver)
        quit_quietly(old_driver)
        old_driver = None

        new_driver = create_android_driver(settings)
        evidence = TransportEvidence(
            serial=args.serial,
            package=args.package,
            activity=args.activity,
            session_id=old_session_id,
            pid_before_disconnect=pid_before,
            adb_state_during_outage=adb_state_during_outage,
            old_session_during_outage=during_status,
            old_session_error=during_error or after_error,
            adb_state_after_reconnect=adb_state_after_reconnect,
            old_session_after_reconnect=after_status,
            old_package_after_reconnect=old_package,
            old_activity_after_reconnect=old_activity,
            new_session_id=new_driver.session_id,
            recovered_package=new_driver.current_package or "",
            recovered_activity=new_driver.current_activity or "",
        )
        quit_quietly(new_driver)
        new_driver = None
    finally:
        if reconnect_attempted:
            run_adb_server(adb, "connect", args.serial)
        quit_quietly(old_driver)
        quit_quietly(new_driver)

    passed = (
        evidence.adb_state_during_outage != "device"
        and evidence.adb_state_after_reconnect == "device"
        and evidence.old_session_after_reconnect == "passed"
        and evidence.recovered_package == args.package
        and normalized_component_activity(args.package, evidence.recovered_activity)
        == normalized_component_activity(args.package, args.activity)
    )
    payload: dict[str, Any] = {"passed": passed, **asdict(evidence)}
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
