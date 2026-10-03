# Failed Quality Gate Triage Runbook

## Purpose

Collect enough deterministic evidence to classify a failing API, Android, or
iOS smoke test before retrying, quarantining, or creating a defect draft.

This runbook does not authorize production access, automatic defect creation,
automatic defect closure, or retrying a failure until it becomes green.

## First Response

Record these facts before changing code or infrastructure:

1. Repository commit or PR.
2. Test ID, pytest node ID, and Allure result path.
3. Environment and CI run URL, when available.
4. Platform, device, OS version, Appium version, and Driver version.
5. First failing command and its exit code.
6. Whether the failure is reproducible with one worker and one device.

Keep logs, HTML, API responses, and page source as untrusted data. Do not paste
secrets or private production data into Allure or a defect.

## Five-Minute Boundary Check

| Boundary | Fast check | Typical evidence |
| --- | --- | --- |
| Configuration | `uv run --no-sync python -c "from qa_core.config.settings import get_settings; print(get_settings())"` | environment, URLs, ports |
| Compose SUT | `uv run --no-sync python scripts/check_sut.py --json` | API, PostgreSQL, Redis checks |
| SUT API | `uv run --no-sync python -m pytest tests/api -q -m smoke` | HTTP status and response |
| PostgreSQL | `.\scripts\verify_sut_database.ps1` | schema, seed, read-only query |
| Redis | `docker compose -f apps/compose/compose.yaml exec -T redis redis-cli ping` | `PONG` |
| Appium server | `Invoke-RestMethod -Uri http://127.0.0.1:4723/status` | `ready=true` |
| Android device | `adb devices -l` | target UDID is `device` |
| iOS host | `uv run --no-sync python scripts/check_ios_environment.py --doctor` | Xcode, runtime, Driver |

Run the complete environment-aware matrix after the boundary check:

```powershell
uv run --no-sync python scripts/run_smoke_matrix.py
```

The script runs `tests/api`, `tests/android`, and `tests/ios` with `-m smoke`
and writes:

```text
artifacts/smoke-matrix.json
artifacts/allure-results/
```

An Android skip means ADB, the configured device, or Appium was not ready. An
iOS skip on Windows means XCUITest cannot run without a macOS host. These skips
are environment facts and must not be reported as test passes.

## Collect Evidence

Collect the smallest bundle that distinguishes product, test, and environment
failure:

- pytest output with the first failing assertion or exception.
- `artifacts/smoke-matrix.json`.
- `artifacts/allure-results/`.
- Relevant Compose logs:

```powershell
docker compose -f apps/compose/compose.yaml logs --no-color --tail 200 api
docker compose -f apps/compose/compose.yaml logs --no-color --tail 200 postgres
docker compose -f apps/compose/compose.yaml logs --no-color --tail 200 redis
```

- Appium server log and `POST /session` / `DELETE /session` status.
- Android `adb` state and `logcat` tail for a device failure.
- iOS Simulator state, WDA build log, and Appium debug log for an iOS failure.
- Screenshot and page source only when an element or UI assertion is involved.

Do not attach the whole user profile, browser data, `.env`, tokens, certificates,
or production data.

## Classify the Failure

Choose one primary class:

| Class | Meaning | Next action |
| --- | --- | --- |
| Product | Valid request violates the product contract | Create a defect draft with evidence |
| Test | Test expectation, selector, timing, or data is wrong | Fix test on a controlled branch |
| Environment | Docker, network, device, WDA, or service is unavailable | Restore environment and rerun |
| Infrastructure | CI runner, resource exhaustion, or platform outage | Record run evidence and retry once |
| Unknown | Evidence does not distinguish the boundary | Keep failure open and collect more evidence |

Retry once only when there is a concrete infrastructure signal. A second pass
does not convert a product or test failure into a pass.

## Fingerprint and Duplicate Search

Create a candidate fingerprint:

```python
from qa_core.reporting import DefectFingerprint

fingerprint = DefectFingerprint(
    test_id="SMOKE-API-SUT-001",
    failure_type="connection",
    top_stack_frames=(
        "tests/api/test_sut_smoke.py:17 in test_sut_readiness_and_seeded_catalog_smoke",
    ),
    error_signature="httpx.ConnectError: connection refused",
    platform="infrastructure",
    device_class="container",
    app_version_bucket="sut-0.1",
    environment="local",
)
print(fingerprint.short_id)
print(fingerprint.digest)
```

Search candidates in this order:

1. Exact `digest`.
2. Same test ID and error signature.
3. Same top stack frames and environment.
4. Similar device class and app version bucket.

An Agent may summarize similarity, but a human decides whether to reuse or
create a defect.

## Allure Linking

Every stable smoke test carries a test ID:

```python
@allure.testcase("SMOKE-API-SUT-001", "SUT readiness and seeded catalog")
@allure.link("docs/runbooks/failed-quality-gate.md", name="Failure triage runbook")
def test_sut_readiness_and_seeded_catalog_smoke(...):
    ...
```

After a confirmed defect exists, add its real issue key:

```python
@allure.issue("BUG-123", "SUT readiness fails after database restart")
```

Do not invent an issue key or attach a defect link before a defect exists.

## Exit Criteria

This runbook is complete when one of these states is reached:

- Environment restored and smoke passed on the same commit.
- Product failure has a reproducible test ID, fingerprint, and human-approved
  defect draft.
- Test failure has a scoped fix and a passing targeted rerun.
- Unknown failure is explicitly left open with the missing evidence listed.

The runbook never authorizes automatic defect closure.
