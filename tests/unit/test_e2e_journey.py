"""Contracts for the Week 23 cross-layer journey and inventory."""

from __future__ import annotations

from pathlib import Path

import pytest
from qa_core.e2e import (
    CatalogItemState,
    E2eContext,
    E2eJourney,
    E2eSetup,
    E2eStepFailure,
)
from qa_core.mobile.platforms import CatalogSnapshot, MobilePlatform

from tests.e2e.support import load_cases

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SetupPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.cleaned = 0

    def prepare(self, context: E2eContext) -> E2eSetup:
        if self.fail:
            raise RuntimeError("setup failed")
        return E2eSetup(
            context=context,
            workspace_slug="qa-run-case",
            item_id=11,
            item_name="Journey item",
            fixture_session_id="s" * 43,
            mobile_base_url="http://127.0.0.1:18000",
        )

    def cleanup(self, setup: E2eSetup) -> None:
        del setup
        self.cleaned += 1


class MobilePort:
    def run(self, setup: E2eSetup) -> CatalogSnapshot:
        return CatalogSnapshot(
            session_id=setup.fixture_session_id,
            item_id=setup.item_id,
            name=setup.item_name,
            status="archived",
        )


class VerificationPort:
    def verify(self, setup: E2eSetup) -> CatalogItemState:
        return CatalogItemState(
            item_id=setup.item_id,
            name=setup.item_name,
            status="archived",
            request_id="request-11",
        )


def _context(tmp_path: Path) -> E2eContext:
    return E2eContext(
        run_id="run23",
        worker_id="gw0",
        test_id="E2E-CAT-001",
        scenario_id="E2E-CATALOG-CROSS-LAYER",
        platform=MobilePlatform.ANDROID,
        artifact_dir=tmp_path,
    )


@pytest.mark.unit
def test_inventory_has_30_unique_cases() -> None:
    cases = load_cases(PROJECT_ROOT / "configs" / "e2e-test-inventory.yaml")

    assert len(cases) == 30
    assert len({case.test_id for case in cases}) == 30


@pytest.mark.unit
def test_e2e_journey_correlates_ui_server_and_evidence(tmp_path: Path) -> None:
    setup = SetupPort()
    result = E2eJourney(
        setup=setup,
        mobile=MobilePort(),
        verification=VerificationPort(),
    ).execute(_context(tmp_path))

    assert result.ui.status == "archived"
    assert result.server.status == "archived"
    assert result.evidence_path is not None
    assert result.evidence_path.exists()
    assert setup.cleaned == 1


@pytest.mark.unit
def test_e2e_journey_preserves_setup_step_and_cleanup(tmp_path: Path) -> None:
    setup = SetupPort(fail=True)

    with pytest.raises(E2eStepFailure) as error:
        E2eJourney(
            setup=setup,
            mobile=MobilePort(),
            verification=VerificationPort(),
        ).execute(_context(tmp_path))

    assert error.value.step_id == "api-setup"
    assert isinstance(error.value.cause, RuntimeError)
    assert setup.cleaned == 0
    assert (tmp_path / "e2e-result.json").exists()
