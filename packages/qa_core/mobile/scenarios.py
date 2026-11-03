"""Typed business scenarios composed from deterministic steps."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from qa_core.mobile.flows import Flow, FlowStep, FlowStepFailure
from qa_core.mobile.platforms import MobilePlatform, PlatformAdapter


class UnsupportedPlatformError(RuntimeError):
    """A scenario was invoked on a platform it does not support."""

    def __init__(self, scenario_id: str, platform: MobilePlatform) -> None:
        self.scenario_id = scenario_id
        self.platform = platform
        super().__init__(
            f"Scenario {scenario_id!r} does not support platform {platform.value!r}"
        )


class ScenarioStepFailure(RuntimeError):
    """Scenario failure that preserves the stable step ID and original cause."""

    def __init__(
        self,
        scenario_id: str,
        step_id: str,
        step_name: str,
        cause: Exception,
    ) -> None:
        self.scenario_id = scenario_id
        self.step_id = step_id
        self.step_name = step_name
        self.cause = cause
        super().__init__(
            f"Scenario {scenario_id!r} failed at {step_id!r} ({step_name!r}): "
            f"{type(cause).__name__}: {cause}"
        )


@dataclass(frozen=True, slots=True)
class ScenarioStep[StateT]:
    """One stable business step that may read from a platform adapter."""

    step_id: str
    name: str
    run: Callable[[StateT, PlatformAdapter], StateT]

    def __post_init__(self) -> None:
        if not self.step_id.strip():
            raise ValueError("scenario step ID must not be empty")
        if not self.name.strip():
            raise ValueError("scenario step name must not be empty")
        if not callable(self.run):
            raise TypeError("scenario step run must be callable")


@dataclass(frozen=True, slots=True)
class MobileScenario[StateT]:
    """A platform-neutral business scenario backed by the existing Flow engine."""

    scenario_id: str
    name: str
    platforms: frozenset[MobilePlatform]
    steps: Sequence[ScenarioStep[StateT]]

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario ID must not be empty")
        if not self.name.strip():
            raise ValueError("scenario name must not be empty")
        if not self.platforms:
            raise ValueError("scenario must support at least one platform")
        if not self.steps:
            raise ValueError("scenario must contain at least one step")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("scenario step IDs must be unique")
        step_names = [step.name for step in self.steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("scenario step names must be unique")

    def run(self, adapter: PlatformAdapter, initial_state: StateT) -> StateT:
        """Run all steps and expose the stable scenario/step identity on failure."""

        if adapter.platform not in self.platforms:
            raise UnsupportedPlatformError(self.scenario_id, adapter.platform)

        flow_steps: list[FlowStep[StateT]] = []
        for step in self.steps:
            def run_step(
                state: StateT,
                scenario_step: ScenarioStep[StateT] = step,
            ) -> StateT:
                return scenario_step.run(state, adapter)

            flow_steps.append(FlowStep(step.name, run_step))
        flow: Flow[StateT] = Flow(self.name, flow_steps)
        try:
            return flow.run(initial_state)
        except FlowStepFailure as exc:
            step = self.steps[exc.step_index]
            raise ScenarioStepFailure(
                self.scenario_id,
                step.step_id,
                step.name,
                exc.cause,
            ) from exc
