"""Compose API setup, mobile action, API verification, and cleanup."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from qa_core.e2e.models import (
    CatalogItemState,
    E2eContext,
    E2eResult,
    E2eSetup,
    E2eStepFailure,
)
from qa_core.mobile.platforms import CatalogSnapshot


class ApiSetupPort(Protocol):
    """Create isolated server state and its short-lived UI capability."""

    def prepare(self, context: E2eContext) -> E2eSetup:
        """Prepare one E2E journey."""

    def cleanup(self, setup: E2eSetup) -> None:
        """Remove server state even when the journey fails."""


class MobileJourneyPort(Protocol):
    """Execute the real mobile portion of one journey."""

    def run(self, setup: E2eSetup) -> CatalogSnapshot:
        """Read and operate the bound fixture item."""


class ApiVerificationPort(Protocol):
    """Verify the final server fact through the normal API."""

    def verify(self, setup: E2eSetup) -> CatalogItemState:
        """Return the server state after the UI action."""


class E2eJourney:
    """Run setup, mobile action, normal API verification, and cleanup."""

    def __init__(
        self,
        *,
        setup: ApiSetupPort,
        mobile: MobileJourneyPort,
        verification: ApiVerificationPort,
    ) -> None:
        self._setup = setup
        self._mobile = mobile
        self._verification = verification

    def execute(self, context: E2eContext) -> E2eResult:
        """Execute one journey and always attempt cleanup."""

        prepared: E2eSetup | None = None
        ui: CatalogSnapshot | None = None
        server: CatalogItemState | None = None
        failure: BaseException | None = None
        failure_step: str | None = None
        evidence_path: Path | None = None
        try:
            try:
                prepared = self._setup.prepare(context)
            except Exception as exc:
                failure_step = "api-setup"
                raise E2eStepFailure(context, "api-setup", exc) from exc

            try:
                ui = self._mobile.run(prepared)
            except Exception as exc:
                failure_step = "mobile-action"
                raise E2eStepFailure(context, "mobile-action", exc) from exc

            try:
                server = self._verification.verify(prepared)
            except Exception as exc:
                failure_step = "api-verification"
                raise E2eStepFailure(context, "api-verification", exc) from exc
        except BaseException as exc:
            failure = exc
            raise
        finally:
            evidence_path = _write_manifest(
                context,
                setup=prepared,
                ui=ui,
                server=server,
                failure=failure,
                failure_step=failure_step,
            )
            if prepared is not None:
                self._setup.cleanup(prepared)
        if prepared is None or ui is None or server is None:
            raise RuntimeError("successful E2E journey did not produce all results")
        return E2eResult(
            setup=prepared,
            ui=ui,
            server=server,
            evidence_path=evidence_path,
        )


def _write_manifest(
    context: E2eContext,
    *,
    setup: E2eSetup | None,
    ui: CatalogSnapshot | None,
    server: CatalogItemState | None,
    failure: BaseException | None,
    failure_step: str | None,
) -> Path:
    context.artifact_dir.mkdir(parents=True, exist_ok=True)
    path = context.artifact_dir / "e2e-result.json"
    payload: dict[str, object] = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "run_id": context.run_id,
        "worker_id": context.worker_id,
        "test_id": context.test_id,
        "scenario_id": context.scenario_id,
        "platform": context.platform.value,
        "setup": asdict(setup) if setup is not None else None,
        "ui": asdict(ui) if ui is not None else None,
        "server": asdict(server) if server is not None else None,
        "failure_step": failure_step,
        "failure_type": type(failure).__name__ if failure is not None else None,
        "failure_message": str(failure) if failure is not None else None,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path
