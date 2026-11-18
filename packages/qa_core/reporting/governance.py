"""Quality ownership and bounded quarantine policy."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class QualityOwners(BaseModel):
    model_config = ConfigDict(frozen=True)

    quality: str = Field(min_length=1)
    api: str = Field(min_length=1)
    android: str = Field(min_length=1)
    ios: str = Field(min_length=1)
    performance: str = Field(min_length=1)
    infrastructure: str = Field(min_length=1)


class QuarantineEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    expires_on: date
    evidence: str = Field(min_length=1)


class QualityGovernance(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: Literal[1]
    owners: QualityOwners
    quarantine: tuple[QuarantineEntry, ...] = ()

    @model_validator(mode="after")
    def validate_unique_quarantine(self) -> QualityGovernance:
        node_ids = [entry.node_id for entry in self.quarantine]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("quarantine node IDs must be unique")
        return self


def load_quality_governance(
    path: Path,
    *,
    today: date,
) -> QualityGovernance:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    governance = QualityGovernance.model_validate(payload)
    expired = [
        entry.node_id
        for entry in governance.quarantine
        if entry.expires_on < today
    ]
    if expired:
        raise ValueError(
            "expired quarantine entries: " + ", ".join(sorted(expired))
        )
    return governance
