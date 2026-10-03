"""Resource-leak evidence for repeated smoke runs.

The same smoke suites must pass on every iteration and the environment must
return to its baseline between runs. This module holds the pure comparison
logic; collecting the snapshots is the caller's responsibility.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_PYTEST_SUMMARY = re.compile(
    r"\d+\s+(?:passed|failed|error|errors|skipped|xfailed|xpassed|deselected)"
)


class EnvironmentSnapshot(BaseModel):
    """Point-in-time view of resources that repeated smoke runs could leak."""

    model_config = ConfigDict(frozen=True)

    captured_at: str
    appium_sessions: tuple[str, ...] = ()
    open_ports: tuple[int, ...] = ()
    processes: dict[str, int] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return self.model_dump(mode="json")


class LeakVerdict(BaseModel):
    """Comparison between a baseline and a final environment snapshot."""

    model_config = ConfigDict(frozen=True)

    session_leak: bool
    port_leak: bool
    process_leak: bool
    new_appium_sessions: tuple[str, ...] = ()
    ports_opened: tuple[int, ...] = ()
    ports_closed: tuple[int, ...] = ()
    process_growth: dict[str, int] = Field(default_factory=dict)

    @property
    def leaked(self) -> bool:
        """Return True when the final snapshot shows a leaked resource."""

        return self.session_leak or self.port_leak or self.process_leak

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation including the verdict."""

        payload = self.model_dump(mode="json")
        payload["leaked"] = self.leaked
        return payload


def compare_snapshots(
    baseline: EnvironmentSnapshot,
    final: EnvironmentSnapshot,
) -> LeakVerdict:
    """Compare two snapshots and report session, port, and process growth.

    ``ports_closed`` is diagnostic rather than a leak: a baseline port that
    disappeared means a service died, which the smoke runs already fail on.
    """

    baseline_sessions = set(baseline.appium_sessions)
    new_sessions = tuple(
        session for session in final.appium_sessions if session not in baseline_sessions
    )

    baseline_ports = set(baseline.open_ports)
    final_ports = set(final.open_ports)
    ports_opened = tuple(sorted(final_ports - baseline_ports))
    ports_closed = tuple(sorted(baseline_ports - final_ports))

    process_growth = {
        name: count - baseline.processes.get(name, 0)
        for name, count in final.processes.items()
        if count > baseline.processes.get(name, 0)
    }

    return LeakVerdict(
        session_leak=bool(new_sessions),
        port_leak=bool(ports_opened),
        process_leak=bool(process_growth),
        new_appium_sessions=new_sessions,
        ports_opened=ports_opened,
        ports_closed=ports_closed,
        process_growth=process_growth,
    )


def parse_pytest_summary(output: str) -> str:
    """Return the last pytest outcome line, or an empty string when absent."""

    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if _PYTEST_SUMMARY.search(stripped):
            return stripped
    return ""
