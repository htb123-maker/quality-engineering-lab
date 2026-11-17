"""Week 30 BrowserStack iOS weak-network and recovery evidence."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import allure
import httpx
import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.ios import IosFixtureAdapter

BUNDLE_ID = "com.example.qaweek19"
NETWORK_BASE_URL_ENV = "QA_IOS_MOBILE_NETWORK_BASE_URL"
DEFAULT_NETWORK_BASE_URL = "http://bs-local.com:8765"
LOSSY_PROFILE = "3g-umts-lossy"
NO_NETWORK_PROFILE = "no-network"
RESET_PROFILE = "reset"

pytestmark = [
    pytest.mark.ios,
    pytest.mark.smoke,
    pytest.mark.timeout(1800),
    pytest.mark.skipif(
        os.getenv("QA_IOS_DEVICE_PROVIDER") != "browserstack",
        reason="Week 30 weak-network acceptance requires BrowserStack.",
    ),
    pytest.mark.skipif(
        os.getenv("QA_IOS_CLOUD_LOCAL", "").lower() not in {"1", "true"},
        reason="Week 30 weak-network acceptance requires BrowserStack Local.",
    ),
]


def _set_session_network(
    settings: Settings,
    session_id: str,
    profile: str,
) -> dict[str, Any]:
    if settings.ios_cloud_user is None or settings.ios_cloud_access_key is None:
        raise RuntimeError("BrowserStack credentials are not configured")
    url = (
        "https://api-cloud.browserstack.com/app-automate/sessions/"
        f"{session_id}/update_network.json"
    )
    response = httpx.put(
        url,
        auth=(
            settings.ios_cloud_user,
            settings.ios_cloud_access_key.get_secret_value(),
        ),
        json={"networkProfile": profile},
        timeout=30,
    )
    return {
        "profile": profile,
        "status_code": response.status_code,
        "accepted": 200 <= response.status_code < 300,
        "response": response.text[:500],
    }


def _open_catalog(
    adapter: IosFixtureAdapter,
    *,
    base_url: str,
) -> tuple[dict[str, Any], float]:
    session_id = uuid4().hex
    started = time.monotonic()
    snapshot = adapter.catalog.open(base_url=base_url, session_id=session_id)
    elapsed_ms = (time.monotonic() - started) * 1000
    return (
        {
            "session_id": session_id,
            "item_id": snapshot.item_id,
            "name": snapshot.name,
            "status": snapshot.status,
            "elapsed_ms": round(elapsed_ms, 3),
        },
        elapsed_ms,
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("Week 30 iOS Weak Network")
@allure.story("Loss, outage, and recovery")
def test_ios_cloud_network_profile_loss_and_recovery(
    settings: Settings,
    project_root: Path,
) -> None:
    """Apply provider network profiles and verify the real app path recovers."""

    network_base_url = os.getenv(NETWORK_BASE_URL_ENV, DEFAULT_NETWORK_BASE_URL)
    output_path = (
        project_root
        / "artifacts"
        / "performance"
        / "week30"
        / "ios-cloud"
        / "weak-network.json"
    )
    driver: WebDriver = create_ios_driver(
        settings.model_copy(update={"ios_bundle_id": BUNDLE_ID})
    )
    session_id = driver.session_id
    if session_id is None:
        driver.quit()
        raise RuntimeError("cloud Appium session did not return a session id")
    adapter = IosFixtureAdapter(
        driver,
        bundle_id=BUNDLE_ID,
        wait_policy=WaitPolicy(timeout_seconds=20.0, poll_interval_seconds=0.5),
        diagnostics_directory=output_path.parent,
    )
    updates: list[dict[str, Any]] = []
    baseline: dict[str, Any]
    lossy: dict[str, Any]
    offline: dict[str, Any]
    recovered: dict[str, Any]

    try:
        adapter.launch_fixture()
        baseline, baseline_ms = _open_catalog(adapter, base_url=network_base_url)

        updates.append(
            _set_session_network(settings, session_id, LOSSY_PROFILE)
        )
        time.sleep(2)
        lossy, lossy_ms = _open_catalog(adapter, base_url=network_base_url)

        updates.append(
            _set_session_network(settings, session_id, NO_NETWORK_PROFILE)
        )
        time.sleep(2)
        offline, _ = _open_catalog(adapter, base_url=network_base_url)

        updates.append(
            _set_session_network(settings, session_id, RESET_PROFILE)
        )
        time.sleep(2)
        recovered, _ = _open_catalog(adapter, base_url=network_base_url)
    finally:
        driver.quit()

    slowdown_ratio = lossy_ms / baseline_ms if baseline_ms > 0 else 0.0
    checks: list[dict[str, Any]] = [
        {
            "name": "baseline_catalog",
            "passed": baseline["status"] == "active",
        },
        {
            "name": "lossy_catalog",
            "passed": lossy["status"] == "active",
        },
        {
            "name": "lossy_is_slower",
            "actual_ratio": round(slowdown_ratio, 3),
            "threshold_ratio": 1.05,
            "passed": slowdown_ratio >= 1.05,
        },
        {
            "name": "offline_is_observable",
            "passed": offline["status"] == "error",
        },
        {
            "name": "network_profile_updates",
            "passed": len(updates) == 3 and all(
                update["accepted"] for update in updates
            ),
        },
        {
            "name": "recovery_after_reset",
            "passed": recovered["status"] == "active",
        },
    ]
    status = "PASS" if all(check["passed"] for check in checks) else "PARTIAL"
    payload = {
        "schema_version": 1,
        "platform": "ios",
        "provider": "browserstack",
        "status": status,
        "session_id": session_id,
        "network_base_url": network_base_url,
        "profiles": {
            "lossy": LOSSY_PROFILE,
            "offline": NO_NETWORK_PROFILE,
            "recovery": RESET_PROFILE,
        },
        "baseline": baseline,
        "lossy": lossy,
        "offline": offline,
        "recovered": recovered,
        "update_responses": updates,
        "slowdown_ratio": round(slowdown_ratio, 3),
        "checks": checks,
        "limitations": [
            "The target is a controlled HTTP fixture reached through BrowserStack Local.",
            "A provider network profile is not packet-level control of the project SUT.",
            "One real iPhone and one profile pair do not cover every weak-network state.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    allure.attach.file(
        str(output_path),
        name="Week 30 iOS weak-network evidence",
        attachment_type=allure.attachment_type.JSON,
    )

    assert (
        checks[0]["passed"]
        and checks[4]["passed"]
        and checks[-1]["passed"]
    ), checks
