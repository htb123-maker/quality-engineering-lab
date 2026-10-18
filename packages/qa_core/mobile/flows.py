"""Deterministic business-flow composition with step-level failures."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FlowStep[StateT]:
    """One named state transition in a business flow."""

    name: str
    run: Callable[[StateT], StateT]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("flow step name must not be empty")


class FlowStepFailure(RuntimeError):
    """Business-flow failure that identifies the exact failing step."""

    def __init__(
        self,
        flow_name: str,
        step_index: int,
        step_name: str,
        cause: Exception,
    ) -> None:
        self.flow_name = flow_name
        self.step_index = step_index
        self.step_name = step_name
        self.cause = cause
        super().__init__(
            f"Flow {flow_name!r} failed at step {step_index + 1} ({step_name!r}): "
            f"{type(cause).__name__}: {cause}"
        )


class Flow[StateT]:
    """Run named state transitions in a fixed order without hidden retries."""

    def __init__(self, name: str, steps: Sequence[FlowStep[StateT]]) -> None:
        if not name.strip():
            raise ValueError("flow name must not be empty")
        if not steps:
            raise ValueError("flow must contain at least one step")
        step_names = [step.name for step in steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("flow step names must be unique")
        self.name = name
        self.steps = tuple(steps)

    def run(self, initial_state: StateT) -> StateT:
        """Execute every step and return the final state."""

        state = initial_state
        for index, step in enumerate(self.steps):
            try:
                state = step.run(state)
            except Exception as exc:
                raise FlowStepFailure(self.name, index, step.name, exc) from exc
        return state
