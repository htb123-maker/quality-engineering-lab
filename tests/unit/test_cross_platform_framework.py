"""Unit contracts for Week 22 cross-platform scenarios and adapters."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from qa_core.mobile.diagnostics import MobileFailureEvidence
from qa_core.mobile.fixture_scenarios import (
    CATALOG_ARCHIVE_SCENARIO,
    FILE_SCENARIO,
    NAVIGATION_SCENARIO,
    CatalogInteractionState,
    FileState,
    NavigationState,
)
from qa_core.mobile.locators import Locator, LocatorStrategy
from qa_core.mobile.platforms import (
    CatalogSnapshot,
    LocatorSet,
    MissingLocatorError,
    MobilePlatform,
    NavigationOutcome,
    PlatformAdapter,
    PlatformAdapterRegistry,
    PlatformCapability,
)
from qa_core.mobile.scenarios import (
    MobileScenario,
    ScenarioStep,
    ScenarioStepFailure,
    UnsupportedPlatformError,
)


class FakeFilePort:
    """In-memory file port with explicit call accounting."""

    def __init__(self) -> None:
        self.content: str | None = None
        self.calls: list[str] = []

    def write_text(self, content: str) -> None:
        self.calls.append("write")
        self.content = content

    def read_text(self) -> str:
        self.calls.append("read")
        if self.content is None:
            raise RuntimeError("file has not been written")
        return self.content

    def cleanup(self) -> None:
        self.calls.append("cleanup")
        self.content = None


class FakeCatalogPort:
    """In-memory API-backed catalog port for shared scenario contracts."""

    def __init__(self) -> None:
        self.session_id = ""
        self.base_url = ""
        self.item_id = 41
        self.name = "API item"
        self.status = "active"
        self.calls: list[str] = []

    def open(self, *, base_url: str, session_id: str) -> CatalogSnapshot:
        self.calls.append("open")
        self.base_url = base_url
        self.session_id = session_id
        return self._snapshot()

    def archive(self) -> CatalogSnapshot:
        self.calls.append("archive")
        self.status = "archived"
        return self._snapshot()

    def _snapshot(self) -> CatalogSnapshot:
        return CatalogSnapshot(
            session_id=self.session_id,
            item_id=self.item_id,
            name=self.name,
            status=self.status,
        )


class FakeAdapter:
    """Small adapter double used by both platform-neutral scenarios."""

    def __init__(
        self,
        platform: MobilePlatform,
        *,
        navigation_outcome: NavigationOutcome = NavigationOutcome.COMPLETED,
    ) -> None:
        self._platform = platform
        self._navigation_outcome = navigation_outcome
        self.files = FakeFilePort()
        self.catalog = FakeCatalogPort()
        self.calls: list[str] = []
        self.locators = LocatorSet(
            platform,
            {
                "fixture.root": Locator(
                    LocatorStrategy.ACCESSIBILITY_ID,
                    "fixture-root",
                )
            },
        )

    @property
    def platform(self) -> MobilePlatform:
        return self._platform

    @property
    def capabilities(self) -> frozenset[PlatformCapability]:
        return frozenset(
            {
                PlatformCapability.NAVIGATION,
                PlatformCapability.FILES,
            }
        )

    def launch_fixture(self) -> None:
        self.calls.append("launch")

    def tap(self, locator_key: str) -> None:
        self.calls.append(f"tap:{locator_key}")

    def text(self, locator_key: str) -> str:
        self.calls.append(f"text:{locator_key}")
        return "fixture"

    def trigger_navigation(self) -> NavigationOutcome:
        self.calls.append("navigate")
        return self._navigation_outcome

    def capture_failure(
        self,
        *,
        scenario_id: str,
        step_id: str,
        error: BaseException,
        context: Mapping[str, object] | None = None,
    ) -> MobileFailureEvidence | None:
        del scenario_id, step_id, error, context
        return None


@pytest.mark.unit
def test_locator_set_resolves_semantic_keys_and_reports_missing_entries() -> None:
    root = Locator(LocatorStrategy.ACCESSIBILITY_ID, "fixture-root")
    locators = LocatorSet(MobilePlatform.IOS, {"fixture.root": root})

    assert locators.get("fixture.root") is root
    assert "fixture.root" in locators
    assert len(locators) == 1

    with pytest.raises(MissingLocatorError) as error:
        locators.get("fixture.navigation_button")

    assert error.value.platform is MobilePlatform.IOS
    assert error.value.key == "fixture.navigation_button"
    assert "fixture.root" in str(error.value)


@pytest.mark.unit
def test_locator_set_requires_all_keys_and_validates_shape() -> None:
    locators = LocatorSet(
        MobilePlatform.ANDROID,
        {
            "fixture.root": Locator(
                LocatorStrategy.RESOURCE_ID,
                "android:id/content",
            )
        },
    )

    with pytest.raises(MissingLocatorError):
        locators.require("fixture.root", "fixture.title")
    with pytest.raises(ValueError, match="locator key"):
        LocatorSet(
            MobilePlatform.ANDROID,
            {"Invalid Key": locators.get("fixture.root")},
        )
    with pytest.raises(ValueError, match="at least one"):
        LocatorSet(MobilePlatform.ANDROID, {})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("platform", "expected_calls"),
    [
        (
            MobilePlatform.ANDROID,
            ["launch", "navigate"],
        ),
        (
            MobilePlatform.IOS,
            ["launch", "navigate"],
        ),
    ],
)
def test_same_navigation_scenario_runs_on_both_platform_adapters(
    platform: MobilePlatform,
    expected_calls: list[str],
) -> None:
    adapter = FakeAdapter(platform)

    state = NAVIGATION_SCENARIO.run(adapter, NavigationState())

    assert state == NavigationState(
        fixture_launched=True,
        outcome=NavigationOutcome.COMPLETED,
    )
    assert adapter.calls == expected_calls


@pytest.mark.unit
@pytest.mark.parametrize("platform", [MobilePlatform.ANDROID, MobilePlatform.IOS])
def test_same_file_scenario_preserves_content_and_cleanup(
    platform: MobilePlatform,
) -> None:
    adapter = FakeAdapter(platform)

    state = FILE_SCENARIO.run(adapter, FileState())

    assert state == FileState(
        payload="week19-file",
        write_completed=True,
        read_content="week19-file",
        cleanup_completed=True,
    )
    assert adapter.files.calls == ["write", "read", "cleanup"]
    assert adapter.files.content is None


@pytest.mark.unit
@pytest.mark.parametrize("platform", [MobilePlatform.ANDROID, MobilePlatform.IOS])
def test_catalog_archive_scenario_uses_the_shared_catalog_port(
    platform: MobilePlatform,
) -> None:
    adapter = FakeAdapter(platform)
    session_id = "s" * 43

    state = CATALOG_ARCHIVE_SCENARIO.run(
        adapter,
        CatalogInteractionState(
            base_url="http://127.0.0.1:18000",
            session_id=session_id,
            expected_name="API item",
        ),
    )

    assert state.initial is not None
    assert state.archived is not None
    assert state.initial.status == "active"
    assert state.archived.status == "archived"
    assert adapter.catalog.calls == ["open", "archive"]


@pytest.mark.unit
def test_scenario_rejects_unsupported_platform_before_running_steps() -> None:
    android_only: MobileScenario[NavigationState] = MobileScenario(
        scenario_id="CP-ANDROID-ONLY",
        name="Android only",
        platforms=frozenset({MobilePlatform.ANDROID}),
        steps=(
            ScenarioStep(
                "launch",
                "launch fixture",
                lambda state, adapter: state,
            ),
        ),
    )
    adapter = FakeAdapter(MobilePlatform.IOS)

    with pytest.raises(UnsupportedPlatformError) as error:
        android_only.run(adapter, NavigationState())

    assert error.value.platform is MobilePlatform.IOS
    assert adapter.calls == []


@pytest.mark.unit
def test_scenario_failure_preserves_step_id_and_original_cause() -> None:
    cause = RuntimeError("navigation endpoint unavailable")

    def fail(state: NavigationState, adapter: PlatformAdapter) -> NavigationState:
        del state, adapter
        raise cause

    scenario = MobileScenario(
        scenario_id="CP-FAIL-001",
        name="failure contract",
        platforms=frozenset({MobilePlatform.ANDROID}),
        steps=(
            ScenarioStep("navigate", "navigate fixture", fail),
        ),
    )

    with pytest.raises(ScenarioStepFailure) as error:
        scenario.run(FakeAdapter(MobilePlatform.ANDROID), NavigationState())

    assert error.value.scenario_id == "CP-FAIL-001"
    assert error.value.step_id == "navigate"
    assert error.value.cause is cause


@pytest.mark.unit
def test_adapter_registry_centralizes_platform_selection() -> None:
    registry = PlatformAdapterRegistry()
    android = FakeAdapter(MobilePlatform.ANDROID)
    registry.register(MobilePlatform.ANDROID, lambda: android)

    assert registry.create(MobilePlatform.ANDROID) is android
    with pytest.raises(LookupError, match="ios"):
        registry.create(MobilePlatform.IOS)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(MobilePlatform.ANDROID, lambda: android)


@pytest.mark.unit
def test_shared_business_scenarios_do_not_contain_platform_branches() -> None:
    project_root = Path(__file__).resolve().parents[2]
    source = (
        project_root / "packages" / "qa_core" / "mobile" / "fixture_scenarios.py"
    ).read_text(encoding="utf-8")

    assert "adapter.platform ==" not in source
    assert "adapter.platform !=" not in source
    assert "adapter.platform is MobilePlatform" not in source
