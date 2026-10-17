"""Create a local defect draft when a pytest call phase fails."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import Literal

import pytest
from _pytest.reports import TestReport

from qa_core.reporting import (
    DefectEvidence,
    DefectFingerprint,
    JsonlDefectDraftStore,
    build_defect_draft,
)

FailureType = Literal["assertion", "timeout", "connection", "configuration", "unknown"]
FailurePlatform = Literal["api", "android", "ios", "cross-platform", "infrastructure"]
_STORE_ATTRIBUTE = "_qa_defect_draft_store"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Expose the draft destination as an explicit pytest option."""

    group = parser.getgroup("quality-engineering-lab")
    group.addoption(
        "--defect-draft-dir",
        action="store",
        default="artifacts/defect-drafts",
        help="Directory for append-only JSONL defect drafts.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Attach one draft store to the pytest session."""

    raw_path = str(config.getoption("--defect-draft-dir")).strip()
    if not raw_path:
        return
    store = JsonlDefectDraftStore(Path(raw_path) / "defects.jsonl")
    setattr(config, _STORE_ATTRIBUTE, store)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[None],
) -> Generator[None, None, None]:
    """Persist a draft after a failure, never creating a formal issue."""

    outcome = yield
    if outcome is None:
        return
    report = outcome.get_result()
    if not isinstance(report, TestReport) or report.when != "call" or not report.failed:
        return

    store = getattr(item.config, _STORE_ATTRIBUTE, None)
    if not isinstance(store, JsonlDefectDraftStore):
        return

    exception = call.excinfo.value if call.excinfo is not None else None
    failure_type = _classify_failure(exception)
    error_signature = _error_signature(exception=exception, report=report)
    first_failure = report.longreprtext.strip() or error_signature
    environment = os.getenv("QA_ENVIRONMENT", "local")
    nodeid = item.nodeid
    test_id = nodeid
    allure_path = _allure_results_path(item.config)

    fingerprint = DefectFingerprint(
        test_id=test_id,
        failure_type=failure_type,
        top_stack_frames=(_first_stack_frame(item),),
        error_signature=error_signature,
        platform=_platform_for(nodeid),
        device_class="container" if _platform_for(nodeid) == "api" else "none",
        app_version_bucket="sut-local",
        environment=environment,
    )
    draft = build_defect_draft(
        fingerprint=fingerprint,
        expected="The test assertion and product contract pass.",
        actual=error_signature,
        reproduction_steps=(f"pytest {nodeid}",),
        evidence=DefectEvidence(
            test_id=test_id,
            pytest_nodeid=nodeid,
            commit=os.getenv("GITHUB_SHA", "unknown"),
            environment=environment,
            command=f"pytest {nodeid}",
            allure_results_path=allure_path,
            ci_run_url=_ci_run_url(),
            first_failure=first_failure[:8000],
        ),
    )
    store.save(draft)


def _classify_failure(exception: BaseException | None) -> FailureType:
    if exception is None:
        return "unknown"
    if isinstance(exception, AssertionError):
        return "assertion"
    exception_name = type(exception).__name__.lower()
    if "timeout" in exception_name:
        return "timeout"
    if any(
        marker in exception_name
        for marker in ("connection", "connect", "transport", "operational")
    ):
        return "connection"
    if any(
        marker in exception_name
        for marker in ("validation", "contract", "configuration")
    ):
        return "configuration"
    return "unknown"


def _error_signature(*, exception: BaseException | None, report: TestReport) -> str:
    if exception is not None:
        signature = f"{type(exception).__name__}: {exception}"
    else:
        lines = [line.strip() for line in report.longreprtext.splitlines() if line.strip()]
        signature = lines[-1] if lines else "pytest reported a failure without details"
    normalized = " ".join(signature.split())
    return normalized[:500] if normalized else "pytest reported a failure without details"


def _first_stack_frame(item: pytest.Item) -> str:
    path, line, function = item.location
    line_number = (line or 0) + 1
    return f"{path}:{line_number} in {function}"


def _platform_for(nodeid: str) -> FailurePlatform:
    normalized = nodeid.replace("\\", "/")
    if "/api/" in normalized:
        return "api"
    if "/android/" in normalized:
        return "android"
    if "/ios/" in normalized:
        return "ios"
    return "infrastructure"


def _allure_results_path(config: pytest.Config) -> str | None:
    try:
        value = config.getoption("--alluredir")
    except ValueError:
        return None
    return str(value) if value else None


def _ci_run_url() -> str | None:
    server = os.getenv("GITHUB_SERVER_URL")
    repository = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    if server and repository and run_id:
        return f"{server}/{repository}/actions/runs/{run_id}"
    return None
