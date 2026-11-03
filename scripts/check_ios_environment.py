"""Check whether the current host can execute an iOS Appium smoke test."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.error import URLError
from urllib.request import urlopen

Profile = Literal["simulator", "device"]
DEFAULT_DEVICE_NAME = "iPhone 16"


@dataclass(frozen=True)
class CheckResult:
    """One environment prerequisite result."""

    name: str
    passed: bool
    detail: str
    required: bool = True
    remediation: str = ""


@dataclass(frozen=True)
class SimulatorSelection:
    """An available iOS Simulator selected from ``simctl`` JSON."""

    name: str
    udid: str
    runtime_version: str
    state: str


def resolve_command(command: Sequence[str]) -> list[str] | None:
    """Resolve an executable and support command wrappers on Windows."""

    executable = shutil.which(command[0])
    if executable is None:
        return None
    if os.name == "nt" and executable.lower().endswith((".bat", ".cmd")):
        command_processor = os.environ.get("COMSPEC", "cmd.exe")
        return [command_processor, "/d", "/c", executable, *command[1:]]
    return [executable, *command[1:]]


def _run_process(
    command: Sequence[str],
    timeout: float,
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    """Run one prerequisite command and return a missing-command detail."""

    resolved = resolve_command(command)
    if resolved is None:
        return None, f"{command[0]} was not found"

    try:
        completed = subprocess.run(
            resolved,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"{command[0]} timed out after {timeout:g}s"
    return completed, None


def run_command(
    name: str,
    command: Sequence[str],
    *,
    timeout: float = 120,
    remediation: str = "",
) -> CheckResult:
    """Run a prerequisite command without failing the whole preflight."""

    completed, missing = _run_process(command, timeout)
    if completed is None:
        return CheckResult(
            name=name,
            passed=False,
            detail=missing or "command did not run",
            remediation=remediation,
        )

    output = (completed.stdout or completed.stderr).strip()
    detail = output.splitlines()[0] if output else f"exit code {completed.returncode}"
    return CheckResult(
        name=name,
        passed=completed.returncode == 0,
        detail=detail,
        remediation=remediation,
    )


def runtime_version(runtime_identifier: str) -> str:
    """Return ``18.5`` from a CoreSimulator iOS runtime identifier."""

    match = re.search(r"iOS-(\d+(?:-\d+)*)", runtime_identifier)
    if match is None:
        return "unknown"
    return match.group(1).replace("-", ".")


def select_simulator(
    payload: dict[str, Any],
    *,
    device_name: str,
    platform_version: str | None,
    udid: str | None,
) -> SimulatorSelection | None:
    """Select one available Simulator, preferring the newest matching runtime."""

    candidates: list[SimulatorSelection] = []
    for runtime_identifier, devices in payload.get("devices", {}).items():
        if not isinstance(runtime_identifier, str) or "iOS-" not in runtime_identifier:
            continue
        version = runtime_version(runtime_identifier)
        if platform_version and version != platform_version:
            continue
        if not isinstance(devices, list):
            continue
        for device in devices:
            if not isinstance(device, dict) or not device.get("isAvailable"):
                continue
            candidate_udid = str(device.get("udid", ""))
            name = str(device.get("name", ""))
            if not candidate_udid:
                continue
            if udid and candidate_udid != udid:
                continue
            if not udid and name != device_name:
                continue
            candidates.append(
                SimulatorSelection(
                    name=name,
                    udid=candidate_udid,
                    runtime_version=version,
                    state=str(device.get("state", "Unknown")),
                )
            )

    if not candidates:
        return None

    def sort_key(candidate: SimulatorSelection) -> tuple[tuple[int, ...], bool]:
        version = tuple(
            int(part)
            for part in candidate.runtime_version.split(".")
            if part.isdigit()
        )
        return version, candidate.state == "Booted"

    return max(candidates, key=sort_key)


def check_xcuitest_driver() -> CheckResult:
    """Confirm that the Appium XCUITest Driver is installed."""

    command = ["appium", "driver", "list", "--installed", "--json"]
    completed, missing = _run_process(command, timeout=120)
    if completed is None:
        return CheckResult(
            name="XCUITest Driver",
            passed=False,
            detail=missing or "Appium did not run",
            remediation="Install Appium 2 and the pinned XCUITest Driver.",
        )
    if completed.returncode != 0:
        return CheckResult(
            name="XCUITest Driver",
            passed=False,
            detail=(completed.stderr or completed.stdout).strip(),
            remediation="Run `appium driver list --installed` and inspect the error.",
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return CheckResult(
            name="XCUITest Driver",
            passed=False,
            detail="Appium returned invalid JSON",
            remediation="Reinstall the pinned Appium and XCUITest Driver versions.",
        )

    driver = payload.get("xcuitest")
    installed = isinstance(driver, dict) and driver.get("installed") is True
    version = driver.get("version", "unknown") if isinstance(driver, dict) else "unknown"
    return CheckResult(
        name="XCUITest Driver",
        passed=installed,
        detail=f"xcuitest@{version}" if installed else "xcuitest is not installed",
        remediation="Run `appium driver install xcuitest@8.4.3`.",
    )


def check_ios_runtimes() -> CheckResult:
    """Confirm that at least one available iOS Simulator runtime is installed."""

    completed, missing = _run_process(
        ["xcrun", "simctl", "list", "runtimes", "-j"],
        timeout=120,
    )
    if completed is None:
        return CheckResult(
            name="iOS runtimes",
            passed=False,
            detail=missing or "xcrun did not run",
            remediation="Install Xcode and select it with `sudo xcode-select -s`.",
        )
    if completed.returncode != 0:
        return CheckResult(
            name="iOS runtimes",
            passed=False,
            detail=(completed.stderr or completed.stdout).strip(),
            remediation="Open Xcode once and install an iOS Simulator runtime.",
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return CheckResult(
            name="iOS runtimes",
            passed=False,
            detail="simctl returned invalid JSON",
            remediation="Check the full `xcrun simctl list runtimes` output.",
        )

    versions = sorted(
        {
            str(runtime.get("version", "unknown"))
            for runtime in payload.get("runtimes", [])
            if isinstance(runtime, dict)
            and runtime.get("isAvailable", True)
            and "iOS" in str(runtime.get("identifier", ""))
        }
    )
    return CheckResult(
        name="iOS runtimes",
        passed=bool(versions),
        detail=f"available={versions}" if versions else "no available iOS runtime",
        remediation="Install an iOS Simulator runtime from Xcode Settings.",
    )


def check_simulator(
    *,
    device_name: str,
    platform_version: str | None,
    udid: str | None,
) -> CheckResult:
    """Confirm that a matching iOS Simulator is available."""

    completed, missing = _run_process(
        ["xcrun", "simctl", "list", "devices", "available", "-j"],
        timeout=120,
    )
    if completed is None:
        return CheckResult(
            name="iOS Simulator",
            passed=False,
            detail=missing or "simctl did not run",
            remediation="Install Xcode and an iOS Simulator runtime.",
        )
    if completed.returncode != 0:
        return CheckResult(
            name="iOS Simulator",
            passed=False,
            detail=(completed.stderr or completed.stdout).strip(),
            remediation="Run `xcrun simctl list devices available` and repair Xcode.",
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return CheckResult(
            name="iOS Simulator",
            passed=False,
            detail="simctl returned invalid JSON",
            remediation="Inspect the raw Simulator inventory output.",
        )

    selected = select_simulator(
        payload,
        device_name=device_name,
        platform_version=platform_version,
        udid=udid,
    )
    if selected is None:
        expected = udid or device_name
        if platform_version:
            expected = f"{expected} on iOS {platform_version}"
        return CheckResult(
            name="iOS Simulator",
            passed=False,
            detail=f"no available Simulator matched {expected}",
            remediation="Create or boot a matching Simulator and set QA_IOS_UDID.",
        )

    return CheckResult(
        name="iOS Simulator",
        passed=True,
        detail=(
            f"{selected.name} ({selected.udid}), iOS {selected.runtime_version}, "
            f"state={selected.state}"
        ),
    )


def parse_codesigning_identities(output: str) -> int | None:
    """Return the number of valid code-signing identities in ``security`` output."""

    match = re.search(r"(\d+)\s+valid identities found", output)
    return int(match.group(1)) if match else None


def check_codesigning_identity() -> CheckResult:
    """Confirm that the Mac has a code-signing identity for a real device."""

    completed, missing = _run_process(
        ["security", "find-identity", "-v", "-p", "codesigning"],
        timeout=60,
    )
    if completed is None:
        return CheckResult(
            name="Code-signing identity",
            passed=False,
            detail=missing or "security did not run",
            remediation="Install an Apple Development certificate in Keychain.",
        )

    output = f"{completed.stdout}\n{completed.stderr}".strip()
    identity_count = parse_codesigning_identities(output)
    if identity_count is not None:
        detail = f"valid_identities={identity_count}"
    elif output:
        detail = output.splitlines()[0]
    else:
        detail = "no identities found"
    return CheckResult(
        name="Code-signing identity",
        passed=completed.returncode == 0 and bool(identity_count),
        detail=detail,
        remediation="Sign in to Xcode with the Apple Developer team and trust the certificate.",
    )


def parse_physical_devices(output: str) -> list[str]:
    """Return visible physical iPhone/iPad names from ``xctrace`` output."""

    devices: list[str] = []
    in_device_section = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line == "== Devices ==":
            in_device_section = True
            continue
        if line.startswith("=="):
            in_device_section = False
            continue
        if not in_device_section or not line:
            continue
        name = line.split("(", maxsplit=1)[0].strip()
        if "iPhone" in name or "iPad" in name:
            devices.append(name)
    return devices


def check_physical_device() -> CheckResult:
    """Confirm that Xcode can see a connected physical iPhone or iPad."""

    completed, missing = _run_process(
        ["xcrun", "xctrace", "list", "devices"],
        timeout=120,
    )
    if completed is None:
        return CheckResult(
            name="Physical iOS device",
            passed=False,
            detail=missing or "xctrace did not run",
            remediation="Connect an unlocked iPhone or iPad and trust this Mac.",
        )
    if completed.returncode != 0:
        return CheckResult(
            name="Physical iOS device",
            passed=False,
            detail=(completed.stderr or completed.stdout).strip(),
            remediation="Open Xcode Devices and Simulators and repair device detection.",
        )

    devices = parse_physical_devices(completed.stdout)
    return CheckResult(
        name="Physical iOS device",
        passed=bool(devices),
        detail=(
            f"visible_devices={len(devices)}, names={devices}"
            if devices
            else "no physical iPhone or iPad is visible"
        ),
        remediation="Unlock the device, trust this Mac, and enable Developer Mode if required.",
    )


def check_appium_server(server_url: str) -> CheckResult:
    """Confirm that a local Appium server is ready to accept sessions."""

    status_url = f"{server_url.rstrip('/')}/status"
    try:
        with urlopen(status_url, timeout=5) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError) as exc:
        return CheckResult(
            name="Appium server",
            passed=False,
            detail=f"{type(exc).__name__}: {exc}",
            remediation="Start `appium --address 127.0.0.1 --port 4723`.",
        )

    value = payload.get("value", payload) if isinstance(payload, dict) else {}
    ready = isinstance(value, dict) and value.get("ready") is True
    build = value.get("build", "unknown") if isinstance(value, dict) else "unknown"
    return CheckResult(
        name="Appium server",
        passed=ready,
        detail=f"ready={ready}, build={build}",
        remediation="Inspect the Appium server log and restart it.",
    )


def collect_checks(
    *,
    profile: Profile,
    device_name: str,
    platform_version: str | None,
    udid: str | None,
    server_url: str | None,
    run_doctor: bool,
) -> list[CheckResult]:
    """Collect local prerequisites without modifying host state."""

    checks = [
        CheckResult(
            name="macOS",
            passed=platform.system() == "Darwin",
            detail=f"platform={platform.system()}",
            remediation="Run XCUITest on macOS, a macOS runner, or a device cloud.",
        ),
        run_command(
            "Xcode path",
            ["xcode-select", "-p"],
            remediation="Install Xcode and run `sudo xcode-select -s /Applications/Xcode.app`.",
        ),
        run_command(
            "Xcode version",
            ["xcodebuild", "-version"],
            remediation="Open Xcode once and accept its license.",
        ),
        check_ios_runtimes(),
    ]
    if profile == "simulator":
        checks.append(
            check_simulator(
                device_name=device_name,
                platform_version=platform_version,
                udid=udid,
            )
        )
    else:
        checks.extend([check_codesigning_identity(), check_physical_device()])

    checks.extend(
        [
            run_command(
                "Appium",
                ["appium", "--version"],
                remediation="Install Appium 2.19.0 on the macOS host.",
            ),
            check_xcuitest_driver(),
        ]
    )
    if server_url:
        checks.append(check_appium_server(server_url))
    if run_doctor and checks[0].passed:
        checks.append(
            run_command(
                "XCUITest doctor",
                ["appium", "driver", "doctor", "xcuitest"],
                timeout=300,
                remediation="Keep the full doctor output with the WDA diagnostic bundle.",
            )
        )
    return checks


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("simulator", "device"),
        default="simulator",
        help="Check the Simulator path or the real-device signing path.",
    )
    parser.add_argument(
        "--device-name",
        default=os.getenv("QA_IOS_DEVICE_NAME", DEFAULT_DEVICE_NAME),
    )
    parser.add_argument(
        "--platform-version",
        default=os.getenv("QA_IOS_PLATFORM_VERSION") or None,
    )
    parser.add_argument(
        "--udid",
        default=os.getenv("QA_IOS_UDID") or None,
    )
    parser.add_argument(
        "--server-url",
        default=None,
        help="Also require a ready Appium server at this URL.",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run the slower Appium XCUITest doctor checks.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the JSON report to this path.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Print iOS environment readiness and return a process exit code."""

    args = parse_args(argv)
    checks = collect_checks(
        profile=args.profile,
        device_name=args.device_name,
        platform_version=args.platform_version,
        udid=args.udid,
        server_url=args.server_url,
        run_doctor=args.doctor,
    )
    passed = all(check.passed for check in checks if check.required)
    payload = {
        "passed": passed,
        "profile": args.profile,
        "device_name": args.device_name,
        "platform_version": args.platform_version,
        "udid": args.udid,
        "server_url": args.server_url,
        "checks": [asdict(check) for check in checks],
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for check in checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"{status} {check.name}: {check.detail}")
            if not check.passed and check.remediation:
                print(f"     remediation: {check.remediation}")
        print(f"iOS {args.profile} environment ready: {passed}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
