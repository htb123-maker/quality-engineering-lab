"""Stable identities and results shared by API and mobile E2E layers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qa_core.mobile.platforms import CatalogSnapshot, MobilePlatform


@dataclass(frozen=True, slots=True)
class CatalogItemState:
    """Server-side catalog state returned by a normal API verification call."""

    item_id: int
    name: str
    status: str
    request_id: str | None = None

    def __post_init__(self) -> None:
        if self.item_id < 1:
            raise ValueError("item_id must be positive")
        if not self.name.strip():
            raise ValueError("catalog item name must not be empty")
        if self.status not in {"active", "archived"}:
            raise ValueError("catalog item status must be active or archived")


@dataclass(frozen=True, slots=True)
class E2eContext:
    """Correlation identity shared by setup, UI, verification, and evidence."""

    run_id: str
    worker_id: str
    test_id: str
    scenario_id: str
    platform: MobilePlatform
    artifact_dir: Path

    def __post_init__(self) -> None:
        for name in ("run_id", "worker_id", "test_id", "scenario_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.platform, MobilePlatform):
            raise TypeError("platform must be a MobilePlatform")


@dataclass(frozen=True, slots=True)
class E2eSetup:
    """API-created state and the short-lived fixture capability used by the UI."""

    context: E2eContext
    workspace_slug: str
    item_id: int
    item_name: str
    fixture_session_id: str
    mobile_base_url: str
    api_request_id: str | None = None
    can_archive: bool = True

    def __post_init__(self) -> None:
        if not self.workspace_slug.strip():
            raise ValueError("workspace_slug must not be empty")
        if self.item_id < 1:
            raise ValueError("item_id must be positive")
        if not self.item_name.strip():
            raise ValueError("item_name must not be empty")
        if len(self.fixture_session_id) < 32:
            raise ValueError("fixture_session_id is too short")
        if not self.mobile_base_url.startswith(("http://", "https://")):
            raise ValueError("mobile_base_url must be an HTTP URL")


@dataclass(frozen=True, slots=True)
class E2eResult:
    """Observed UI and server facts from one completed cross-layer journey."""

    setup: E2eSetup
    ui: CatalogSnapshot
    server: CatalogItemState
    evidence_path: Path | None = None


class E2eStepFailure(RuntimeError):
    """E2E failure with stable scenario and step identity."""

    def __init__(
        self,
        context: E2eContext,
        step_id: str,
        cause: BaseException,
    ) -> None:
        self.context = context
        self.step_id = step_id
        self.cause = cause
        super().__init__(
            f"E2E scenario {context.scenario_id!r} failed at {step_id!r}: "
            f"{type(cause).__name__}: {cause}"
        )
