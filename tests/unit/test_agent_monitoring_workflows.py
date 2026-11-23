"""Workflow contracts for the runtime Agent monitoring path."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).parents[2]
PIPELINE_PATH = (
    PROJECT_ROOT / ".github" / "workflows" / "week31-quality-pipeline.yml"
)
IOS_CLOUD_PATH = PROJECT_ROOT / ".github" / "workflows" / "ios-fixture-cloud.yml"


def _workflow(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _step(workflow: dict[str, Any], job: str, name: str) -> dict[str, Any]:
    steps = workflow["jobs"][job]["steps"]
    return next(step for step in steps if step.get("name") == name)


def test_quality_pipeline_runs_monitor_and_requires_full_evidence() -> None:
    workflow = _workflow(PIPELINE_PATH)

    ai_eval = _step(
        workflow,
        "ai-eval",
        "Run deterministic evidence triage eval",
    )
    assert "--require-human-review" in ai_eval["run"]

    monitor = _step(
        workflow,
        "trends",
        "Run CI and performance monitoring agents",
    )
    assert "ai.agents.artifact_monitor" in monitor["run"]
    assert "--fail-on-incomplete" in monitor["run"]

    trends = _step(workflow, "trends", "Build trends")
    assert "--require-pipeline-checks" in trends["run"]
    assert "--fail-on-incomplete" in trends["run"]


def test_ios_cloud_upload_403_becomes_blocked_evidence() -> None:
    workflow = _workflow(IOS_CLOUD_PATH)

    upload = _step(
        workflow,
        "ios-fixture-cloud",
        "Upload fixture to BrowserStack",
    )
    run = upload["run"]
    assert '"$status" = "403"' in run
    assert "ios-cloud-status.json" in run
    assert '"status":"BLOCKED"' in run
    assert "CLOUD_BLOCKED=true" in run

    week19 = _step(
        workflow,
        "ios-fixture-cloud",
        "Run Week 19 acceptance cases",
    )
    assert "env.CLOUD_BLOCKED != 'true'" in week19["if"]
