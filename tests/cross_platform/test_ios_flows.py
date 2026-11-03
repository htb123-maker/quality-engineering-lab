"""iOS execution of the shared Week 22 fixture scenarios."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import allure
import pytest
from qa_core.mobile.fixture_scenarios import (
    FILE_SCENARIO,
    NAVIGATION_SCENARIO,
    FileState,
    NavigationState,
)
from qa_core.platforms.ios import IosFixtureAdapter

from tests.cross_platform.support import run_with_evidence

pytestmark = [
    pytest.mark.ios,
    pytest.mark.smoke,
    pytest.mark.timeout(900),
]


@allure.epic("Quality Engineering Lab")
@allure.feature("Cross-platform framework")
@allure.story("Shared fixture scenarios")
@allure.testcase("CP-FIXTURE-NAV-001", "iOS shared navigation scenario")
def test_ios_runs_shared_navigation_scenario(
    ios_cross_platform_adapter: IosFixtureAdapter,
) -> None:
    state = run_with_evidence(
        NAVIGATION_SCENARIO,
        ios_cross_platform_adapter,
        NavigationState(),
    )

    assert state.fixture_launched is True
    assert state.outcome is not None


@allure.epic("Quality Engineering Lab")
@allure.feature("Cross-platform framework")
@allure.story("Shared fixture scenarios")
@allure.testcase("CP-FIXTURE-FILE-001", "iOS shared file scenario")
def test_ios_runs_shared_file_scenario(
    ios_cross_platform_adapter: IosFixtureAdapter,
) -> None:
    state = run_with_evidence(
        FILE_SCENARIO,
        ios_cross_platform_adapter,
        FileState(),
    )

    assert state.read_content == state.payload
    assert state.cleanup_completed is True
