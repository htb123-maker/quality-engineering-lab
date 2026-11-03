"""Shared Week 22 fixture scenarios with platform-neutral business assertions."""

from dataclasses import dataclass, replace

from qa_core.mobile.platforms import (
    MobilePlatform,
    NavigationOutcome,
    PlatformAdapter,
)
from qa_core.mobile.scenarios import MobileScenario, ScenarioStep

SUPPORTED_PLATFORMS = frozenset(
    {
        MobilePlatform.ANDROID,
        MobilePlatform.IOS,
    }
)
FIXTURE_FILE_CONTENT = "week19-file"


@dataclass(frozen=True, slots=True)
class NavigationState:
    """Observed state of the shared fixture navigation scenario."""

    fixture_launched: bool = False
    outcome: NavigationOutcome | None = None


@dataclass(frozen=True, slots=True)
class FileState:
    """Observed state of the shared fixture file round-trip scenario."""

    payload: str = FIXTURE_FILE_CONTENT
    write_completed: bool = False
    read_content: str | None = None
    cleanup_completed: bool = False


def _launch_fixture(
    state: NavigationState,
    adapter: PlatformAdapter,
) -> NavigationState:
    adapter.launch_fixture()
    return replace(state, fixture_launched=True)


def _trigger_navigation(
    state: NavigationState,
    adapter: PlatformAdapter,
) -> NavigationState:
    return replace(state, outcome=adapter.trigger_navigation())


def _assert_navigation(
    state: NavigationState,
    adapter: PlatformAdapter,
) -> NavigationState:
    del adapter
    assert state.fixture_launched, "fixture must launch before navigation"
    assert state.outcome is NavigationOutcome.COMPLETED, (
        f"navigation must complete, observed {state.outcome!r}"
    )
    return state


def _write_file(
    state: FileState,
    adapter: PlatformAdapter,
) -> FileState:
    adapter.files.write_text(state.payload)
    return replace(state, write_completed=True)


def _read_file(
    state: FileState,
    adapter: PlatformAdapter,
) -> FileState:
    return replace(state, read_content=adapter.files.read_text())


def _assert_file_round_trip(
    state: FileState,
    adapter: PlatformAdapter,
) -> FileState:
    del adapter
    assert state.write_completed, "file write must complete before read"
    assert state.read_content == state.payload, (
        "file round trip must return the written payload; "
        f"expected {state.payload!r}, observed {state.read_content!r}"
    )
    return state


def _cleanup_file(
    state: FileState,
    adapter: PlatformAdapter,
) -> FileState:
    adapter.files.cleanup()
    return replace(state, cleanup_completed=True)


NAVIGATION_SCENARIO = MobileScenario(
    scenario_id="CP-FIXTURE-NAV-001",
    name="fixture navigation completes",
    platforms=SUPPORTED_PLATFORMS,
    steps=(
        ScenarioStep("launch", "launch fixture", _launch_fixture),
        ScenarioStep("navigate", "trigger fixture navigation", _trigger_navigation),
        ScenarioStep("assert-navigation", "verify navigation outcome", _assert_navigation),
    ),
)

FILE_SCENARIO = MobileScenario(
    scenario_id="CP-FIXTURE-FILE-001",
    name="fixture file round trip",
    platforms=SUPPORTED_PLATFORMS,
    steps=(
        ScenarioStep("write", "write fixture text", _write_file),
        ScenarioStep("read", "read fixture text", _read_file),
        ScenarioStep(
            "assert-content",
            "verify file round trip",
            _assert_file_round_trip,
        ),
        ScenarioStep("cleanup", "delete fixture text", _cleanup_file),
    ),
)
