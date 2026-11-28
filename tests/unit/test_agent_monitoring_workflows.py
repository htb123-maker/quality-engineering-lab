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

    upload = next(
        step
        for step in workflow["jobs"]["trends"]["steps"]
        if step.get("uses") == "actions/upload-artifact@v4"
    )
    assert "artifacts/collected/agent-monitor.json" in upload["with"]["path"]


def test_quality_pipeline_reuses_prebuilt_wda_derived_data() -> None:
    workflow = _workflow(PIPELINE_PATH)
    ios_job = workflow["jobs"]["ios-simulator"]

    assert ios_job["env"]["QA_IOS_USE_NEW_WDA"] == "true"

    cache = _step(workflow, "ios-simulator", "Restore prebuilt WebDriverAgent")
    assert cache["uses"] == "actions/cache@v4"
    assert "artifacts/wda-derived" in cache["with"]["path"]
    assert "appium2.19.0" in cache["with"]["key"]
    assert "xcuitest8.4.3" in cache["with"]["key"]

    prebuild = _step(workflow, "ios-simulator", "Prebuild WebDriverAgent")
    run = prebuild["run"]
    assert 'wda_derived_data="$GITHUB_WORKSPACE/artifacts/wda-derived"' in run
    assert '-derivedDataPath "$wda_derived_data"' in run
    assert (
        'printf \'QA_IOS_DERIVED_DATA_PATH=%s\\n\' "$wda_derived_data" '
        '>> "$GITHUB_ENV"'
    ) in run


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
