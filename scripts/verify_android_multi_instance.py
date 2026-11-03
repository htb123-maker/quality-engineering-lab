"""Verify two Android Appium instances against two distinct devices."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from qa_core.config.settings import Settings  # noqa: E402
from qa_core.driver.android import create_android_driver  # noqa: E402

DEFAULT_PACKAGE = "com.example.qaweek15"
DEFAULT_ACTIVITY = ".MainActivity"


@dataclass(frozen=True)
class InstanceEvidence:
    """One Appium instance and device observation."""

    label: str
    server_url: str
    requested_serial: str
    session_id: str
    capability_udid: str
    package: str
    activity: str
    window_width: int
    window_height: int
    counter_text: str
    status: str
    error: str


def build_settings(
    base: Settings,
    *,
    label: str,
    server_url: str,
    serial: str,
    package: str,
    activity: str,
) -> Settings:
    """Build settings targeting one Appium endpoint and Android device."""

    return base.model_copy(
        update={
            "appium_server_url": server_url,
            "android_udid": serial,
            "android_device_name": label,
            "android_app_package": package,
            "android_app_activity": activity,
        }
    )


def find_by_accessibility(driver: WebDriver, value: str) -> WebElement:
    """Find one fixture control through a stable accessibility id."""

    return driver.find_element(AppiumBy.ACCESSIBILITY_ID, value)


def counter_value(text: str) -> str:
    """Extract the final numeric counter value independent of language."""

    match = re.search(r"(\d+)\s*$", text)
    return match.group(1) if match else ""


def probe_instance(
    *,
    label: str,
    server_url: str,
    serial: str,
    package: str,
    activity: str,
    increment_count: int,
) -> InstanceEvidence:
    """Create one session and mutate only that device's fixture state."""

    settings = build_settings(
        Settings(),
        label=label,
        server_url=server_url,
        serial=serial,
        package=package,
        activity=activity,
    )
    driver: WebDriver | None = None
    try:
        driver = create_android_driver(settings)
        driver.implicitly_wait(5)
        find_by_accessibility(driver, "fixture-reset").click()
        for _ in range(increment_count):
            find_by_accessibility(driver, "fixture-counter").click()
        time.sleep(0.5)
        counter_text = find_by_accessibility(
            driver,
            "fixture-counter-value",
        ).text
        size = driver.get_window_size()
        capabilities = driver.capabilities
        capability_udid = str(
            capabilities.get("udid")
            or capabilities.get("deviceUDID")
            or ""
        )
        return InstanceEvidence(
            label=label,
            server_url=server_url,
            requested_serial=serial,
            session_id=driver.session_id,
            capability_udid=capability_udid,
            package=driver.current_package or "",
            activity=driver.current_activity or "",
            window_width=int(size["width"]),
            window_height=int(size["height"]),
            counter_text=counter_text,
            status="passed",
            error="",
        )
    except Exception as exc:  # noqa: BLE001
        return InstanceEvidence(
            label=label,
            server_url=server_url,
            requested_serial=serial,
            session_id=driver.session_id if driver is not None else "",
            capability_udid="",
            package="",
            activity="",
            window_width=0,
            window_height=0,
            counter_text="",
            status="failed",
            error=f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
        )
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001
                pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-url", default="http://127.0.0.1:4723")
    parser.add_argument("--primary-serial", required=True)
    parser.add_argument("--secondary-url", default="http://127.0.0.1:4724")
    parser.add_argument("--secondary-serial", required=True)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--activity", default=DEFAULT_ACTIVITY)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run both sessions concurrently and print one machine-readable result."""

    args = parse_args(argv)
    probes = (
        {
            "label": "physical-android",
            "server_url": args.primary_url,
            "serial": args.primary_serial,
            "package": args.package,
            "activity": args.activity,
            "increment_count": 1,
        },
        {
            "label": "avd-secondary",
            "server_url": args.secondary_url,
            "serial": args.secondary_serial,
            "package": args.package,
            "activity": args.activity,
            "increment_count": 2,
        },
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(probe_instance, **probe) for probe in probes]
        instances = [future.result() for future in futures]

    session_ids = {instance.session_id for instance in instances if instance.session_id}
    expected_counters = ("1", "2")
    passed = (
        all(instance.status == "passed" for instance in instances)
        and len(session_ids) == 2
        and all(instance.capability_udid == instance.requested_serial for instance in instances)
        and all(instance.package == args.package for instance in instances)
        and {instance.activity for instance in instances} == {args.activity}
        and tuple(counter_value(instance.counter_text) for instance in instances)
        == expected_counters
    )
    payload: dict[str, Any] = {
        "passed": passed,
        "instances": [asdict(instance) for instance in instances],
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
