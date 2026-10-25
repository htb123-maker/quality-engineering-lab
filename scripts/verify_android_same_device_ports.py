"""Verify two concurrent Appium sessions on one device with isolated ports."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from appium.webdriver.webdriver import WebDriver

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from qa_core.config.settings import Settings  # noqa: E402
from qa_core.driver.android import create_android_driver  # noqa: E402

DEFAULT_PACKAGE = "com.example.qaweek15"
DEFAULT_ACTIVITY = ".MainActivity"


@dataclass(frozen=True)
class SessionEvidence:
    """One of two sessions sharing the same Android device."""

    label: str
    server_url: str
    serial: str
    requested_system_port: int
    requested_mjpeg_port: int
    session_id: str
    capability_udid: str
    system_port: int
    mjpeg_server_port: int
    package: str
    activity: str
    status: str
    error: str


def build_settings(
    base: Settings,
    *,
    label: str,
    server_url: str,
    serial: str,
    system_port: int,
    mjpeg_server_port: int,
    package: str,
    activity: str,
) -> Settings:
    """Bind one Appium endpoint to one device with unique local service ports."""

    return base.model_copy(
        update={
            "appium_server_url": server_url,
            "android_udid": serial,
            "android_device_name": label,
            "android_system_port": system_port,
            "android_mjpeg_server_port": mjpeg_server_port,
            "android_app_package": package,
            "android_app_activity": activity,
        }
    )


def probe_session(
    *,
    label: str,
    server_url: str,
    serial: str,
    system_port: int,
    mjpeg_server_port: int,
    package: str,
    activity: str,
) -> SessionEvidence:
    """Create one session and report capabilities plus foreground state."""

    settings = build_settings(
        Settings(),
        label=label,
        server_url=server_url,
        serial=serial,
        system_port=system_port,
        mjpeg_server_port=mjpeg_server_port,
        package=package,
        activity=activity,
    )
    driver: WebDriver | None = None
    try:
        driver = create_android_driver(settings)
        capabilities = driver.capabilities
        return SessionEvidence(
            label=label,
            server_url=server_url,
            serial=serial,
            requested_system_port=system_port,
            requested_mjpeg_port=mjpeg_server_port,
            session_id=driver.session_id,
            capability_udid=str(
                capabilities.get("udid")
                or capabilities.get("deviceUDID")
                or ""
            ),
            system_port=int(capabilities.get("systemPort", 0)),
            mjpeg_server_port=int(capabilities.get("mjpegServerPort", 0)),
            package=driver.current_package or "",
            activity=driver.current_activity or "",
            status="passed",
            error="",
        )
    except Exception as exc:  # noqa: BLE001
        return SessionEvidence(
            label=label,
            server_url=server_url,
            serial=serial,
            requested_system_port=system_port,
            requested_mjpeg_port=mjpeg_server_port,
            session_id=driver.session_id if driver is not None else "",
            capability_udid="",
            system_port=0,
            mjpeg_server_port=0,
            package="",
            activity="",
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
    parser.add_argument("--serial", required=True)
    parser.add_argument("--primary-url", default="http://127.0.0.1:4723")
    parser.add_argument("--secondary-url", default="http://127.0.0.1:4724")
    parser.add_argument("--primary-system-port", type=int, default=8200)
    parser.add_argument("--secondary-system-port", type=int, default=8201)
    parser.add_argument("--primary-mjpeg-port", type=int, default=7810)
    parser.add_argument("--secondary-mjpeg-port", type=int, default=7811)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--activity", default=DEFAULT_ACTIVITY)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run both same-device sessions concurrently and return an exit code."""

    args = parse_args(argv)
    probes = (
        {
            "label": "same-device-primary",
            "server_url": args.primary_url,
            "serial": args.serial,
            "system_port": args.primary_system_port,
            "mjpeg_server_port": args.primary_mjpeg_port,
            "package": args.package,
            "activity": args.activity,
        },
        {
            "label": "same-device-secondary",
            "server_url": args.secondary_url,
            "serial": args.serial,
            "system_port": args.secondary_system_port,
            "mjpeg_server_port": args.secondary_mjpeg_port,
            "package": args.package,
            "activity": args.activity,
        },
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(probe_session, **probe) for probe in probes]
        sessions = [future.result() for future in futures]

    session_ids = {session.session_id for session in sessions if session.session_id}
    passed = (
        all(session.status == "passed" for session in sessions)
        and len(session_ids) == 2
        and len({session.system_port for session in sessions}) == 2
        and len({session.mjpeg_server_port for session in sessions}) == 2
        and all(session.capability_udid == args.serial for session in sessions)
        and all(session.package == args.package for session in sessions)
    )
    payload: dict[str, Any] = {
        "passed": passed,
        "serial": args.serial,
        "sessions": [asdict(session) for session in sessions],
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
