"""Week 20 parallel iOS Simulator matrix acceptance."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import allure
import pytest
from qa_core.config.settings import Settings
from qa_core.driver.ios import build_ios_options, create_ios_driver
from qa_core.platforms.ios import IosDeviceProfile, IosWorkerResources


@allure.epic("Quality Engineering Lab")
@allure.feature("iOS Device Matrix")
@allure.story("Parallel Simulator isolation")
@pytest.mark.ios
@pytest.mark.smoke
@pytest.mark.skipif(
    sys.platform != "darwin"
    or os.getenv("QA_IOS_DEVICE_PROVIDER", "local").lower() != "local",
    reason="Week 20 parallel matrix requires macOS and a local simulator.",
)
@pytest.mark.timeout(1200)
def test_week20_parallel_simulator_session(
    ios_worker_settings: Settings,
    ios_worker_profile: IosDeviceProfile,
    ios_worker_resources: IosWorkerResources,
    project_root: Path,
) -> None:
    """Prove each worker gets a distinct device, WDA port, and DerivedData path."""

    capabilities = build_ios_options(ios_worker_settings).to_capabilities()
    expected_port = ios_worker_resources.wda_local_port
    assert expected_port is not None
    assert capabilities["appium:udid"] == ios_worker_profile.udid
    assert capabilities["appium:wdaLocalPort"] == expected_port
    assert capabilities["appium:derivedDataPath"] == str(
        ios_worker_resources.derived_data_path
    )

    evidence_root = (
        project_root
        / "artifacts"
        / "ios-week20"
        / ios_worker_resources.run_id
    )
    ready_dir = evidence_root / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    ready_path = ready_dir / f"{ios_worker_profile.device_id}.json"
    result_path = evidence_root / f"{ios_worker_profile.device_id}.json"

    started_at = time.time()
    record: dict[str, Any] = {
        "device_id": ios_worker_profile.device_id,
        "role": ios_worker_profile.role,
        "udid": ios_worker_profile.udid,
        "appium_server_port": ios_worker_resources.appium_server_port,
        "appium_server_url": str(ios_worker_settings.appium_server_url),
        "wda_local_port": expected_port,
        "derived_data_path": str(ios_worker_resources.derived_data_path),
        "worker_index": ios_worker_resources.worker_index,
        "worker_count": ios_worker_resources.worker_count,
        "started_at": started_at,
    }

    driver = create_ios_driver(ios_worker_settings)
    completed = False
    try:
        ready_path.write_text(
            json.dumps(record, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        _wait_for_workers(ready_dir, ios_worker_resources.worker_count)
        window_size = driver.get_window_size()
        assert window_size["width"] > 0
        assert window_size["height"] > 0
        record["window_size"] = window_size
        completed = True

        allure.dynamic.parameter("ios_device", ios_worker_profile.device_id)
        allure.dynamic.parameter("ios_role", ios_worker_profile.role)
        allure.dynamic.parameter("ios_udid", ios_worker_profile.udid or "")
        allure.dynamic.parameter(
            "ios_appium_port",
            str(ios_worker_resources.appium_server_port),
        )
        allure.dynamic.parameter("ios_wda_port", str(expected_port))
        allure.attach(
            json.dumps(record, indent=2, sort_keys=True),
            name="iOS worker resources",
            attachment_type=allure.attachment_type.JSON,
        )
        allure.attach(
            driver.get_screenshot_as_png(),
            name="iOS matrix session screenshot",
            attachment_type=allure.attachment_type.PNG,
        )
    finally:
        driver.quit()
        record["ended_at"] = time.time()
        record["completed"] = completed
        result_path.write_text(
            json.dumps(record, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _wait_for_workers(ready_dir: Path, expected_workers: int) -> None:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if len(tuple(ready_dir.glob("*.json"))) >= expected_workers:
            return
        time.sleep(0.2)
    raise AssertionError(
        f"expected {expected_workers} active iOS workers in {ready_dir}"
    )
