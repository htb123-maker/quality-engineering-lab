# Week 31 Quality Pipeline

## Purpose

One commit starts the deterministic quality path:

```text
quality gates
-> Compose SUT
-> Android Linux emulator
-> iOS real-device cloud
-> performance smoke
-> trend / owner / quarantine evidence
```

Workflow: `.github/workflows/week31-quality-pipeline.yml`

## Triggers

- Pull request: quality, SUT, Android, and eligible iOS cloud jobs.
- Push to `main` or the Week 31 study branch: all jobs.
- Nightly and weekly schedule: all jobs.
- Manual `workflow_dispatch`.

The trend job runs with `if: always()` so failed evidence is still indexed.

## Job Boundaries

| Job | Real environment | Required evidence |
| --- | --- | --- |
| `quality` | Ubuntu runner | Ruff, Mypy, unit JUnit/Allure, governance JSON |
| `sut` | Docker Compose | readiness, integration/API JUnit, Compose logs |
| `android` | Linux Android emulator | APK build, Appium smoke, JUnit/Allure/logs |
| `ios-cloud` | BrowserStack real iPhone | JUnit/Allure for session and launch evidence |
| `performance` | Isolated Compose SUT | Locust CSV/JSON and SLO result |
| `trends` | Aggregated artifacts | history JSON and HTML |

## Secrets And Variables

Required secrets:

```text
IOS_CLOUD_USER
IOS_CLOUD_ACCESS_KEY
```

Required repository variable:

```text
IOS_CLOUD_APP
```

The iOS job is skipped when the fixture App variable is absent. A skipped cloud
job does not count as iOS PASS.

## Local Validation

```powershell
uv run python scripts/check_quality_governance.py
uv run pytest tests/unit/test_quality_trends.py -q
uv run python scripts/build_quality_trends.py `
  --artifacts-root artifacts `
  --run-id local `
  --commit HEAD `
  --json-output artifacts/quality-trends/history.json `
  --html-output artifacts/quality-trends/index.html
```

## Failure Triage

1. Read the job name and the first failed step.
2. Download the named artifact.
3. Use JUnit for deterministic test failure and Allure for attachments.
4. Inspect `artifacts/defect-drafts/defects.jsonl` for a draft; it is not a
   formal issue.
5. Follow `docs/runbooks/failed-quality-gate.md`.
6. Keep provider/runner cancellation separate from product/test failure.

## Trend And Governance

`configs/quality-governance.yaml` defines owners and bounded quarantine.
Expired quarantine entries fail the quality job.

The trend job restores a bounded GitHub Actions cache, appends the current run,
and uploads:

```text
artifacts/quality-trends/history.json
artifacts/quality-trends/index.html
```

The cache is trend input, not a source of truth. Raw JUnit, Allure, Locust, and
device artifacts remain attached to the run.
