"""Week 32 read-only monitoring agent registry contracts."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ai.agents.registry import AgentRegistry, load_agent_registry

PROJECT_ROOT = Path(__file__).parents[2]
REGISTRY_PATH = PROJECT_ROOT / "ai" / "agents" / "registry.yaml"


def test_registry_contains_five_read_only_monitoring_agents() -> None:
    registry = load_agent_registry(REGISTRY_PATH)

    assert {agent.id for agent in registry.agents} == {
        "ci-monitor",
        "flaky-monitor",
        "ios-environment-monitor",
        "performance-monitor",
        "weekly-maintenance",
    }
    for agent in registry.agents:
        assert agent.permissions.mode == "read_only"
        assert agent.permissions.write_access is False
        assert agent.permissions.can_execute_shell is False
        assert agent.permissions.can_create_defects is False
        assert agent.permissions.can_close_defects is False
        assert agent.failure_fallback == "INSUFFICIENT_EVIDENCE"


def test_registry_rejects_write_access() -> None:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    payload["agents"][0]["permissions"]["write_access"] = True

    with pytest.raises(ValidationError, match="write_access"):
        AgentRegistry.model_validate(payload)
