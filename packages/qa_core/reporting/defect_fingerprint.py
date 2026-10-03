"""Stable defect fingerprints for duplicate detection and triage."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

FailurePlatform = Literal["api", "android", "ios", "cross-platform", "infrastructure"]


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


class DefectFingerprint(BaseModel):
    """Normalized facts used to find likely duplicate failures."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    test_id: str
    failure_type: str
    top_stack_frames: tuple[str, ...] = ()
    error_signature: str
    platform: FailurePlatform
    device_class: str = "none"
    app_version_bucket: str = "unknown"
    environment: str

    @field_validator("top_stack_frames")
    @classmethod
    def normalize_stack_frames(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > 5:
            raise ValueError("top_stack_frames must contain at most five frames")

        normalized = tuple(_collapse_whitespace(frame) for frame in value)
        if any(not frame for frame in normalized):
            raise ValueError("top_stack_frames cannot contain empty frames")
        return normalized

    @field_validator("error_signature")
    @classmethod
    def normalize_error_signature(cls, value: str) -> str:
        normalized = _collapse_whitespace(value)
        if not normalized:
            raise ValueError("error_signature cannot be empty")
        return normalized

    @property
    def canonical_payload(self) -> dict[str, object]:
        """Return the JSON-compatible canonical fingerprint input."""

        return self.model_dump(mode="json")

    @property
    def digest(self) -> str:
        """Return the full SHA-256 digest used for exact duplicate lookup."""

        canonical_json = json.dumps(
            self.canonical_payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @property
    def short_id(self) -> str:
        """Return a human-readable identifier derived from the full digest."""

        return f"FPR-{self.digest[:16].upper()}"
