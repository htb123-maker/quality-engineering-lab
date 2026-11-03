"""Verify Android Appium endpoints, including cross-host device-pool entries."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from appium.webdriver.webdriver import WebDriver

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from qa_core.config.settings import Settings  # noqa: E402
from qa_core.driver.android import create_android_driver  # noqa: E402


@dataclass(frozen=True)
class PoolEndpoint:
    """One Appium endpoint and its host-local Android device."""

    name: str
    appium_url: str
    serial: str
    system_port: int
    mjpeg_server_port: int


@dataclass(frozen=True)
class PoolEvidence:
    """One device-pool session observation."""

    name: str
    appium_url: str
    appium_host: str
    serial: str
    system_port: int
    mjpeg_server_port: int
    session_id: str
    capability_udid: str
    package: str
    activity: str
    status: str
    error: str


def _port(value: Any, field: str, endpoint_index: int) -> int:
    if not isinstance(value, int) or not 1024 <= value <= 65535:
        raise ValueError(
            f"endpoint[{endpoint_index}].{field} must be an integer from 1024 to 65535"
        )
    return value


def load_pool(path: Path) -> tuple[PoolEndpoint, ...]:
    """Load and validate a YAML Appium device pool."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw_endpoints = payload.get("endpoints") if isinstance(payload, dict) else None
    if not isinstance(raw_endpoints, list) or not raw_endpoints:
        raise ValueError("pool must contain a non-empty endpoints list")

    endpoints: list[PoolEndpoint] = []
    names: set[str] = set()
    targets: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_endpoints):
        if not isinstance(raw, dict):
            raise ValueError(f"endpoint[{index}] must be a mapping")
        name = str(raw.get("name", "")).strip()
        appium_url = str(raw.get("appium_url", "")).strip().rstrip("/")
        serial = str(raw.get("serial", "")).strip()
        if not name or not appium_url or not serial:
            raise ValueError(f"endpoint[{index}] requires name, appium_url, and serial")
        parsed = urlsplit(appium_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(f"endpoint[{index}].appium_url is invalid")
        if name in names:
            raise ValueError(f"duplicate endpoint name: {name}")
        target = (appium_url, serial)
        if target in targets:
            raise ValueError(f"duplicate endpoint target: {appium_url} / {serial}")
        names.add(name)
        targets.add(target)
        endpoints.append(
            PoolEndpoint(
                name=name,
                appium_url=appium_url,
                serial=serial,
                system_port=_port(raw.get("system_port"), "system_port", index),
                mjpeg_server_port=_port(
                    raw.get("mjpeg_server_port"),
                    "mjpeg_server_port",
                    index,
                ),
            )
        )
    return tuple(endpoints)


def probe_endpoint(endpoint: PoolEndpoint, package: str, activity: str) -> PoolEvidence:
    """Create one read-only session through a pool endpoint."""

    settings = Settings().model_copy(
        update={
            "appium_server_url": endpoint.appium_url,
            "android_udid": endpoint.serial,
            "android_device_name": endpoint.name,
            "android_system_port": endpoint.system_port,
            "android_mjpeg_server_port": endpoint.mjpeg_server_port,
            "android_app_package": package,
            "android_app_activity": activity,
        }
    )
    driver: WebDriver | None = None
    try:
        driver = create_android_driver(settings)
        capabilities = driver.capabilities
        return PoolEvidence(
            name=endpoint.name,
            appium_url=endpoint.appium_url,
            appium_host=urlsplit(endpoint.appium_url).hostname or "",
            serial=endpoint.serial,
            system_port=endpoint.system_port,
            mjpeg_server_port=endpoint.mjpeg_server_port,
            session_id=driver.session_id,
            capability_udid=str(
                capabilities.get("udid")
                or capabilities.get("deviceUDID")
                or ""
            ),
            package=driver.current_package or "",
            activity=driver.current_activity or "",
            status="passed",
            error="",
        )
    except Exception as exc:  # noqa: BLE001
        return PoolEvidence(
            name=endpoint.name,
            appium_url=endpoint.appium_url,
            appium_host=urlsplit(endpoint.appium_url).hostname or "",
            serial=endpoint.serial,
            system_port=endpoint.system_port,
            mjpeg_server_port=endpoint.mjpeg_server_port,
            session_id=driver.session_id if driver is not None else "",
            capability_udid="",
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
    parser.add_argument("--pool-config", type=Path, required=True)
    parser.add_argument("--package", default="com.example.qaweek15")
    parser.add_argument("--activity", default=".MainActivity")
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run every configured pool endpoint concurrently."""

    args = parse_args(argv)
    endpoints = load_pool(args.pool_config)
    with ThreadPoolExecutor(max_workers=len(endpoints)) as executor:
        futures = [
            executor.submit(
                probe_endpoint,
                endpoint,
                args.package,
                args.activity,
            )
            for endpoint in endpoints
        ]
        evidence = [future.result() for future in futures]
    session_ids = {item.session_id for item in evidence if item.session_id}
    passed = (
        all(item.status == "passed" for item in evidence)
        and len(session_ids) == len(evidence)
        and all(item.capability_udid == item.serial for item in evidence)
        and all(item.package == args.package for item in evidence)
    )
    payload: dict[str, Any] = {
        "passed": passed,
        "endpoint_count": len(endpoints),
        "host_count": len({item.appium_host for item in evidence}),
        "sessions": [asdict(item) for item in evidence],
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
