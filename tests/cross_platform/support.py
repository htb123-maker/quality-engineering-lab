"""Helpers for executing shared scenarios with platform failure evidence."""

from __future__ import annotations

from qa_core.mobile.platforms import PlatformAdapter
from qa_core.mobile.scenarios import MobileScenario, ScenarioStepFailure


def run_with_evidence[StateT](
    scenario: MobileScenario[StateT],
    adapter: PlatformAdapter,
    initial_state: StateT,
) -> StateT:
    """Run a scenario and persist evidence before re-raising a step failure."""

    try:
        return scenario.run(adapter, initial_state)
    except ScenarioStepFailure as exc:
        adapter.capture_failure(
            scenario_id=exc.scenario_id,
            step_id=exc.step_id,
            error=exc.cause,
        )
        raise
