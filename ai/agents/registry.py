"""Typed registry for the first read-only monitoring agents."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

READ_ONLY_TOOLS = frozenset(
    {
        "read_adr_and_runbooks",
        "read_allure_artifacts",
        "read_ci_metadata",
        "read_device_preflight",
        "read_failure_fingerprints",
        "read_metrics",
        "read_performance_artifacts",
        "read_repository_docs",
        "read_runner_logs",
        "read_test_results",
        "read_trend_history",
        "read_weekly_reports",
    }
)
REQUIRED_OUTPUTS = frozenset(
    {
        "confidence",
        "evidence_paths",
        "outcome",
        "proposed_actions",
        "requires_human_approval",
        "suspected_layer",
    }
)


class AgentPermissions(BaseModel):
    """Hard boundaries shared by every agent in this registry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["read_only"]
    write_access: Literal[False]
    can_execute_shell: Literal[False]
    can_create_defects: Literal[False]
    can_close_defects: Literal[False]
    can_modify_thresholds: Literal[False]
    can_merge_or_release: Literal[False]
    human_approval_required_for_proposed_actions: Literal[True]


class AgentDefinition(BaseModel):
    """Input, output, tools, and failure behavior for one agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    purpose: str = Field(min_length=1)
    triggers: tuple[str, ...] = Field(min_length=1)
    inputs: tuple[str, ...] = Field(min_length=1)
    tool_allowlist: tuple[str, ...] = Field(min_length=1)
    outputs: tuple[str, ...] = Field(min_length=1)
    evidence_required: Literal[True]
    failure_fallback: Literal["INSUFFICIENT_EVIDENCE"]
    permissions: AgentPermissions

    @model_validator(mode="after")
    def validate_read_only_contract(self) -> AgentDefinition:
        unknown_tools = set(self.tool_allowlist) - READ_ONLY_TOOLS
        if unknown_tools:
            raise ValueError(
                f"agent {self.id} uses non-read-only tools: "
                + ", ".join(sorted(unknown_tools))
            )
        missing_outputs = REQUIRED_OUTPUTS - set(self.outputs)
        if missing_outputs:
            raise ValueError(
                f"agent {self.id} misses required outputs: "
                + ", ".join(sorted(missing_outputs))
            )
        return self


class AgentRegistry(BaseModel):
    """Versioned collection of agents approved for read-only monitoring."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    agents: tuple[AgentDefinition, ...] = Field(min_length=5)

    @model_validator(mode="after")
    def validate_unique_agents(self) -> AgentRegistry:
        agent_ids = [agent.id for agent in self.agents]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("agent IDs must be unique")
        return self


def load_agent_registry(path: Path) -> AgentRegistry:
    """Load and validate an agent registry from a local YAML file."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AgentRegistry.model_validate(payload)
