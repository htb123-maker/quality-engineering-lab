"""Shared Week 22 fixture scenarios with platform-neutral business assertions."""

from dataclasses import dataclass, replace

from qa_core.mobile.platforms import (
    CatalogSnapshot,
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


@dataclass(frozen=True, slots=True)
class CatalogInteractionState:
    """Observed state of an API-backed catalog fixture interaction."""

    base_url: str
    session_id: str
    expected_name: str
    initial: CatalogSnapshot | None = None
    archived: CatalogSnapshot | None = None


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


def _open_catalog(
    state: CatalogInteractionState,
    adapter: PlatformAdapter,
) -> CatalogInteractionState:
    return replace(
        state,
        initial=adapter.catalog.open(
            base_url=state.base_url,
            session_id=state.session_id,
        ),
    )


def _assert_catalog_open(
    state: CatalogInteractionState,
    adapter: PlatformAdapter,
) -> CatalogInteractionState:
    del adapter
    assert state.initial is not None, "catalog session must load before assertion"
    assert state.initial.name == state.expected_name, (
        "mobile catalog must load the API-created item; "
        f"expected {state.expected_name!r}, observed {state.initial.name!r}"
    )
    assert state.initial.status == "active", (
        f"mobile catalog item must start active, observed {state.initial.status!r}"
    )
    return state


def _archive_catalog(
    state: CatalogInteractionState,
    adapter: PlatformAdapter,
) -> CatalogInteractionState:
    return replace(state, archived=adapter.catalog.archive())


def _assert_catalog_archived(
    state: CatalogInteractionState,
    adapter: PlatformAdapter,
) -> CatalogInteractionState:
    del adapter
    assert state.archived is not None, "catalog archive must return a snapshot"
    assert state.initial is not None, "catalog must be opened before archive assertion"
    assert state.archived.item_id == state.initial.item_id
    assert state.archived.name == state.expected_name
    assert state.archived.status == "archived"
    return state


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


CATALOG_ARCHIVE_SCENARIO = MobileScenario(
    scenario_id="E2E-CATALOG-ARCHIVE-001",
    name="API-backed catalog item is archived through the mobile app",
    platforms=SUPPORTED_PLATFORMS,
    steps=(
        ScenarioStep("open", "open API-backed catalog item", _open_catalog),
        ScenarioStep(
            "assert-open",
            "verify API-created item is visible",
            _assert_catalog_open,
        ),
        ScenarioStep("archive", "archive item through mobile UI", _archive_catalog),
        ScenarioStep(
            "assert-archived",
            "verify mobile archive result",
            _assert_catalog_archived,
        ),
    ),
)
