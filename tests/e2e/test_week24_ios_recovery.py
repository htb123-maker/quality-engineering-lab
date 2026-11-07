"""Week 24 iOS recovery acceptance on a real device cloud."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from appium.webdriver.webdriver import WebDriver
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver
from qa_core.e2e import (
    FaultSpec,
    FaultType,
    RecoveryContext,
    RecoveryJourney,
)
from qa_core.mobile.waits import WaitPolicy
from qa_core.platforms.ios import IosFixtureAdapter

CLOUD_PROVIDERS = {"browserstack", "saucelabs", "lambdatest"}

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.ios,
    pytest.mark.recovery,
    pytest.mark.skipif(
        os.getenv("QA_IOS_DEVICE_PROVIDER", "local").lower() not in CLOUD_PROVIDERS,
        reason="Week 24 iOS recovery requires a configured device cloud.",
    ),
]


def _bundle_id(settings: Settings) -> str:
    value = settings.ios_bundle_id.strip()
    if not value:
        raise ValueError("QA_IOS_BUNDLE_ID must not be empty")
    return value


def _new_adapter(
    driver: WebDriver,
    *,
    bundle_id: str,
    project_root: Path,
    test_id: str,
) -> IosFixtureAdapter:
    return IosFixtureAdapter(
        driver,
        bundle_id=bundle_id,
        wait_policy=WaitPolicy(timeout_seconds=60.0, poll_interval_seconds=0.5),
        diagnostics_directory=(
            project_root / "artifacts" / "e2e" / "week24" / test_id / "ios"
        ),
    )


def _fixture_fact(
    driver: WebDriver,
    adapter: IosFixtureAdapter,
) -> dict[str, object]:
    adapter.launch_fixture()
    return {
        "session_id": driver.session_id,
        "title": adapter.text("fixture.title"),
        "platform": str(driver.capabilities.get("platformName", "")),
    }


def _verify_fixture_fact(fact: dict[str, object]) -> None:
    assert fact["session_id"]
    assert fact["title"] == "QA iOS Fixture"
    assert str(fact["platform"]).lower() == "ios"


@pytest.mark.timeout(1800)
def test_ios_cloud_process_termination_recovers_fixture(
    settings: Settings,
    project_root: Path,
) -> None:
    """Terminate the app and recover it inside the same cloud Appium session."""

    test_id = "W24-IOS-CLOUD-001"
    bundle_id = _bundle_id(settings)
    driver = create_ios_driver(settings)
    adapter = _new_adapter(
        driver,
        bundle_id=bundle_id,
        project_root=project_root,
        test_id=test_id,
    )

    def observe_stopped_state() -> dict[str, Any]:
        state = driver.query_app_state(bundle_id)
        return {"app_state": int(state)}

    def terminate_fixture() -> None:
        driver.terminate_app(bundle_id)

    try:
        result = RecoveryJourney[dict[str, object], dict[str, Any]](
            baseline=lambda: _fixture_fact(driver, adapter),
            inject=terminate_fixture,
            observe=observe_stopped_state,
            remove=adapter.launch_fixture,
            probe=lambda: {
                "session_id": driver.session_id,
                "title": adapter.text("fixture.title"),
                "platform": str(driver.capabilities.get("platformName", "")),
            },
            is_recovered=lambda fact: fact["title"] == "QA iOS Fixture",
            verify=_verify_fixture_fact,
        ).execute(
            RecoveryContext(
                run_id=uuid4().hex[:8],
                worker_id="ios-cloud",
                test_id=test_id,
                scenario_id="RECOVERY-IOS-CLOUD-PROCESS",
                platform="ios",
                artifact_dir=(
                    project_root
                    / "artifacts"
                    / "e2e"
                    / "week24"
                    / test_id
                    / "ios"
                ),
            ),
            FaultSpec(
                fault_type=FaultType.APP_PROCESS_LOST,
                target=bundle_id,
                expected_boundary="cloud app is not running after terminate",
                timeout_seconds=120.0,
                cleanup_action="activate the app and wait for the fixture title",
            ),
        )

        assert result.observed["app_state"] != 4
        assert result.recovered["session_id"] == driver.session_id
    finally:
        driver.quit()


@pytest.mark.timeout(1800)
def test_ios_cloud_session_rebuild_recovers_fixture(
    settings: Settings,
    project_root: Path,
) -> None:
    """Quit the cloud session and prove a new session reaches the fixture."""

    test_id = "W24-IOS-CLOUD-002"
    bundle_id = _bundle_id(settings)
    first_driver = create_ios_driver(settings)
    first_adapter = _new_adapter(
        first_driver,
        bundle_id=bundle_id,
        project_root=project_root,
        test_id=test_id,
    )
    recovered_driver: WebDriver | None = None
    recovered_adapter: IosFixtureAdapter | None = None
    first_session_id = first_driver.session_id
    first_quit = False

    def quit_first_session() -> None:
        nonlocal first_quit
        first_driver.quit()
        first_quit = True

    def rebuild_session() -> None:
        nonlocal recovered_driver, recovered_adapter
        recovered_driver = create_ios_driver(settings)
        recovered_adapter = _new_adapter(
            recovered_driver,
            bundle_id=bundle_id,
            project_root=project_root,
            test_id=test_id,
        )
        recovered_adapter.launch_fixture()

    def probe_rebuilt_session() -> dict[str, object]:
        assert recovered_driver is not None
        assert recovered_adapter is not None
        return {
            "session_id": recovered_driver.session_id,
            "title": recovered_adapter.text("fixture.title"),
            "platform": str(
                recovered_driver.capabilities.get("platformName", "")
            ),
        }

    def verify_rebuilt_session(fact: dict[str, object]) -> None:
        _verify_fixture_fact(fact)
        assert fact["session_id"] != first_session_id

    try:
        result = RecoveryJourney[dict[str, object], dict[str, object]](
            baseline=lambda: _fixture_fact(first_driver, first_adapter),
            inject=quit_first_session,
            observe=lambda: {
                "old_session_id": first_session_id,
                "released": first_quit,
            },
            remove=rebuild_session,
            probe=probe_rebuilt_session,
            is_recovered=lambda fact: (
                fact["title"] == "QA iOS Fixture"
                and fact["session_id"] != first_session_id
            ),
            verify=verify_rebuilt_session,
        ).execute(
            RecoveryContext(
                run_id=uuid4().hex[:8],
                worker_id="ios-cloud",
                test_id=test_id,
                scenario_id="RECOVERY-IOS-CLOUD-SESSION",
                platform="ios",
                artifact_dir=(
                    project_root
                    / "artifacts"
                    / "e2e"
                    / "week24"
                    / test_id
                    / "ios"
                ),
            ),
            FaultSpec(
                fault_type=FaultType.SESSION_LOST,
                target="browserstack-appium-session",
                expected_boundary="the original cloud Appium session is released",
                timeout_seconds=300.0,
                cleanup_action="create a new cloud Appium session and reopen the fixture",
            ),
        )

        assert result.observed["released"] is True
        assert result.recovered["session_id"] != first_session_id
    finally:
        if recovered_driver is not None:
            recovered_driver.quit()
        if not first_quit:
            first_driver.quit()
