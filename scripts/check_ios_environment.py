"""Check whether the current host can execute the iOS Appium smoke test."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CheckResult:
    """One environment prerequisite result."""

    name: str
    passed: bool
    detail: str


def resolve_command(command: Sequence[str]) -> list[str] | None:
    """Resolve an executable and support command wrappers on Windows."""

    executable = shutil.which(command[0])
    if executable is None:
        return None
    if os.name == "nt" and executable.lower().endswith((".bat", ".cmd")):
        command_processor = os.environ.get("COMSPEC", "cmd.exe")
        return [command_processor, "/d", "/c", executable, *command[1:]]
    return [executable, *command[1:]]


def run_command(name: str, command: Sequence[str]) -> CheckResult:
    """Run a prerequisite command without failing the whole preflight."""

    resolved = resolve_command(command)
    if resolved is None:
        return CheckResult(name=name, passed=False, detail=f"{command[0]} was not found")

    completed = subprocess.run(
        resolved,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip()
    detail = output.splitlines()[0] if output else f"exit code {completed.returncode}"
    return CheckResult(name=name, passed=completed.returncode == 0, detail=detail)


def check_xcuitest_driver() -> CheckResult:
    """Confirm that the Appium XCUITest Driver is installed."""

    command = ["appium", "driver", "list", "--installed", "--json"]
    resolved = resolve_command(command)
    if resolved is None:
        return CheckResult(
            name="XCUITest Driver",
            passed=False,
            detail="appium was not found",
        )

    completed = subprocess.run(
        resolved,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        return CheckResult(
            name="XCUITest Driver",
            passed=False,
            detail=(completed.stderr or completed.stdout).strip(),
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return CheckResult(
            name="XCUITest Driver",
            passed=False,
            detail="Appium returned invalid JSON",
        )

    driver = payload.get("xcuitest")
    installed = isinstance(driver, dict) and driver.get("installed") is True
    version = driver.get("version", "unknown") if isinstance(driver, dict) else "unknown"
    return CheckResult(
        name="XCUITest Driver",
        passed=installed,
        detail=f"xcuitest@{version}" if installed else "xcuitest is not installed",
    )


def collect_checks(run_doctor: bool) -> list[CheckResult]:
    """Collect all local prerequisites without modifying host state."""

    checks = [
        CheckResult(
            name="macOS",
            passed=platform.system() == "Darwin",
            detail=f"platform={platform.system()}",
        ),
        run_command("Xcode path", ["xcode-select", "-p"]),
        run_command("iOS runtimes", ["xcrun", "simctl", "list", "runtimes"]),
        run_command("Appium", ["appium", "--version"]),
        check_xcuitest_driver(),
    ]
    if run_doctor and checks[0].passed:
        checks.append(run_command("XCUITest doctor", ["appium", "driver", "doctor", "xcuitest"]))
    return checks


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run the slower Appium XCUITest doctor checks.",
    )
    return parser.parse_args()


def main() -> int:
    """Print iOS environment readiness and return a process exit code."""

    args = parse_args()
    checks = collect_checks(run_doctor=args.doctor)
    passed = all(check.passed for check in checks)

    if args.json:
        payload = {
            "passed": passed,
            "checks": [asdict(check) for check in checks],
        }
        print(json.dumps(payload, indent=2))
    else:
        for check in checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"{status} {check.name}: {check.detail}")
        print(f"iOS environment ready: {passed}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
