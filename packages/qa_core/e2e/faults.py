"""Reversible fault specifications shared by API and mobile recovery tests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

FaultParameter = str | int | float | bool | None


class FaultType(StrEnum):
    """Fault families that Week 24 can inject and remove deterministically."""

    NETWORK_LATENCY = "network_latency"
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_RESET = "network_reset"
    PROXY_DISABLED = "proxy_disabled"
    SERVICE_UNAVAILABLE = "service_unavailable"
    RATE_LIMIT = "rate_limit"
    APP_PROCESS_LOST = "app_process_lost"
    SESSION_LOST = "session_lost"
    ADB_TRANSPORT_LOST = "adb_transport_lost"
    WDA_SESSION_LOST = "wda_session_lost"


@dataclass(frozen=True, slots=True)
class FaultSpec:
    """One bounded, reversible fault and the boundary it should exercise."""

    fault_type: FaultType
    target: str
    expected_boundary: str
    timeout_seconds: float = 30.0
    cleanup_action: str = "remove injected fault"
    parameters: tuple[tuple[str, FaultParameter], ...] = ()

    def __post_init__(self) -> None:
        if not self.target.strip():
            raise ValueError("fault target must not be empty")
        if not self.expected_boundary.strip():
            raise ValueError("expected_boundary must not be empty")
        if not self.cleanup_action.strip():
            raise ValueError("cleanup_action must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        parameter_names = [name for name, _ in self.parameters]
        if any(not name.strip() for name in parameter_names):
            raise ValueError("fault parameter names must not be empty")
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError("fault parameter names must be unique")

    @property
    def parameter_map(self) -> dict[str, FaultParameter]:
        """Return parameters as a copy for diagnostic serialization."""

        return dict(self.parameters)
