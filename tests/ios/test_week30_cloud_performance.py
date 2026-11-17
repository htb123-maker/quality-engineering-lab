"""Week 30 BrowserStack iOS launch and UI-ready timing evidence."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

import allure
import httpx
import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.ios import IosFixtureAdapter
from selenium.webdriver.support.ui import WebDriverWait

CLOUD_PROVIDERS = {"browserstack", "saucelabs", "lambdatest"}
BUNDLE_ID = "com.example.qaweek19"
COLD_CYCLES = 5
WARM_CYCLES = 5
COLD_P95_LIMIT_MS = 8_000.0
WARM_P95_LIMIT_MS = 3_000.0

pytestmark = [
    pytest.mark.ios,
    pytest.mark.smoke,
    pytest.mark.timeout(1800),
    pytest.mark.skipif(
        os.getenv("QA_IOS_DEVICE_PROVIDER", "local").lower()
        not in CLOUD_PROVIDERS,
        reason="Week 30 iOS performance requires a configured device cloud.",
    ),
]


def _percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentage / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(_percentile(values, 95), 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
    }


def _new_adapter(
    driver: WebDriver,
    project_root: Path,
) -> IosFixtureAdapter:
    return IosFixtureAdapter(
        driver,
        bundle_id=BUNDLE_ID,
        wait_policy=WaitPolicy(timeout_seconds=60.0, poll_interval_seconds=0.5),
        diagnostics_directory=(
            project_root / "artifacts" / "performance" / "week30" / "ios-cloud"
        ),
    )


def _wait_fixture_ready(
    driver: WebDriver,
    adapter: IosFixtureAdapter,
) -> None:
    adapter._wait.visible(  # noqa: SLF001
        driver,
        adapter.locators.get("fixture.root"),
    )
    adapter.wait_text("fixture.title", "QA iOS Fixture")


def _send_fixture_home(driver: WebDriver) -> None:
    driver.execute_script("mobile: pressButton", {"name": "home"})
    WebDriverWait(driver, timeout=10, poll_frequency=0.25).until(
        lambda active_driver: active_driver.query_app_state(BUNDLE_ID) != 4
    )


def _sanitized_capabilities(driver: WebDriver) -> dict[str, Any]:
    allowed = {
        "platformName",
        "platformVersion",
        "deviceName",
        "automationName",
        "app",
        "bundleId",
        "browserstack.sessionId",
        "networkProfile",
    }
    return {
        key: value
        for key, value in driver.capabilities.items()
        if key in allowed
    }


def _browserstack_session_summary(
    settings: Settings,
    session_id: str,
) -> dict[str, Any]:
    """Fetch a sanitized provider session record after release."""

    if settings.ios_device_provider != "browserstack":
        return {"status": "NOT_APPLICABLE", "provider": settings.ios_device_provider}
    if settings.ios_cloud_user is None or settings.ios_cloud_access_key is None:
        return {"status": "NOT_AVAILABLE", "reason": "credentials are not configured"}

    url = (
        "https://api-cloud.browserstack.com/app-automate/sessions/"
        f"{session_id}.json"
    )
    auth = (
        settings.ios_cloud_user,
        settings.ios_cloud_access_key.get_secret_value(),
    )
    allowed = {
        "name",
        "status",
        "duration",
        "device",
        "os",
        "os_version",
        "browser_url",
        "video_url",
        "appium_logs_url",
        "device_logs_url",
        "build_name",
        "project_name",
        "network_profile",
    }
    last_error = ""
    for _ in range(6):
        try:
            response = httpx.get(url, auth=auth, timeout=20)
            if response.status_code == 200:
                payload = response.json()
                session = payload.get("automation_session", payload)
                return {
                    "status": "AVAILABLE",
                    "record": {
                        key: session[key]
                        for key in allowed
                        if key in session
                    },
                }
            last_error = f"HTTP {response.status_code}"
        except (httpx.HTTPError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(5)
    return {"status": "NOT_AVAILABLE", "reason": last_error}


@allure.epic("Quality Engineering Lab")
@allure.feature("Week 30 iOS Cloud Performance")
@allure.story("Cloud launch and UI-ready timing")
def test_ios_cloud_launch_and_resume_timing(
    settings: Settings,
    project_root: Path,
) -> None:
    """Measure real cloud Appium launch commands and fixture UI readiness."""

    output_path = (
        project_root
        / "artifacts"
        / "performance"
        / "week30"
        / "ios-cloud"
        / "mobile-performance.json"
    )
    session_started_at = time.monotonic()
    driver = create_ios_driver(
        settings.model_copy(update={"ios_bundle_id": BUNDLE_ID})
    )
    session_ready_ms = (time.monotonic() - session_started_at) * 1000
    adapter = _new_adapter(driver, project_root)
    cold: list[float] = []
    warm: list[float] = []
    session_id = driver.session_id
    if session_id is None:
        driver.quit()
        raise RuntimeError("cloud Appium session did not return a session id")
    capabilities = _sanitized_capabilities(driver)
    provider_session: dict[str, Any]

    try:
        adapter.launch_fixture()
        for _ in range(COLD_CYCLES):
            driver.terminate_app(BUNDLE_ID)
            started = time.monotonic()
            driver.activate_app(BUNDLE_ID)
            _wait_fixture_ready(driver, adapter)
            cold.append((time.monotonic() - started) * 1000)

        for _ in range(WARM_CYCLES):
            adapter.launch_fixture()
            _send_fixture_home(driver)
            started = time.monotonic()
            driver.activate_app(BUNDLE_ID)
            _wait_fixture_ready(driver, adapter)
            warm.append((time.monotonic() - started) * 1000)
    finally:
        driver.quit()
        provider_session = _browserstack_session_summary(settings, session_id)

    cold_summary = _summary(cold)
    warm_summary = _summary(warm)
    checks: list[dict[str, Any]] = [
        {
            "name": "session_ready",
            "actual_ms": round(session_ready_ms, 3),
            "limit_ms": 180_000,
            "passed": session_ready_ms <= 180_000,
        },
        {
            "name": "cold_activate_to_ui_p95",
            "actual_ms": cold_summary["p95_ms"],
            "limit_ms": COLD_P95_LIMIT_MS,
            "passed": float(cold_summary["p95_ms"]) <= COLD_P95_LIMIT_MS,
        },
        {
            "name": "warm_background_to_ui_p95",
            "actual_ms": warm_summary["p95_ms"],
            "limit_ms": WARM_P95_LIMIT_MS,
            "passed": float(warm_summary["p95_ms"]) <= WARM_P95_LIMIT_MS,
        },
        {
            "name": "provider_session_record",
            "passed": provider_session["status"] == "AVAILABLE",
        },
    ]
    status = "PASS" if all(check["passed"] for check in checks) else "PARTIAL"
    payload = {
        "schema_version": 1,
        "platform": "ios",
        "provider": settings.ios_device_provider,
        "status": status,
        "session_id": session_id,
        "session_ready_ms": round(session_ready_ms, 3),
        "capabilities": capabilities,
        "cold": {
            "definition": "terminateApp -> activateApp -> fixture title visible",
            "samples_ms": [round(value, 3) for value in cold],
            "summary": cold_summary,
        },
        "warm": {
            "definition": "pressButton(home) -> activateApp -> fixture title visible",
            "samples_ms": [round(value, 3) for value in warm],
            "summary": warm_summary,
        },
        "provider_session": provider_session,
        "checks": checks,
        "limitations": [
            "Timing includes Appium command transport to the device cloud.",
            "activateApp success is not the same as first-frame rendering.",
            "This is not an Instruments, xctrace, or MetricKit measurement.",
            "One cloud device and OS version do not represent the full iOS matrix.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        "WEEK30_IOS_PERFORMANCE_EVIDENCE="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    allure.attach.file(
        str(output_path),
        name="Week 30 iOS cloud performance",
        attachment_type=allure.attachment_type.JSON,
    )

    assert all(check["passed"] for check in checks), checks
