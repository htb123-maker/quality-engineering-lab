# Fault Recovery Triage / 故障恢复排障

## Start Order / 启动顺序

1. Start the local SUT with the fault-injection profile.
2. Verify API, PostgreSQL, Redis, and Toxiproxy health.
3. Run the recovery contract tests.
4. Run the six API network/service/rate-limit cases.
5. Run the two Android process and ADB/session cases.
6. Run one Week 23 cross-layer Gate G0 case.
7. Run the two iOS device-cloud recovery cases through GitHub Actions.
8. Verify test namespace, proxy, Appium session, and ADB reverse cleanup.

```powershell
.\scripts\start_sut.ps1 -FaultInjection -WaitSeconds 180
uv run --no-sync python -m pytest tests\unit\test_recovery_journey.py -q
uv run --no-sync python -m pytest tests\e2e\test_week24_network_recovery.py -q
```

If the worktree `.venv` is not synchronized, use the already verified project
interpreter with `PYTHONPATH` pointed at the active worktree:

```powershell
$env:PYTHONPATH="$PWD\packages;$PWD\src"
& '<project-root>\.venv\Scripts\python.exe' -m pytest `
  tests\e2e\test_week24_network_recovery.py -q
```

## Triage Order / 排障顺序

| Symptom | First check | Classification |
| --- | --- | --- |
| Recovery never passes | proxy upstream, service health, API request IDs | environment or product |
| Observed state is unexpectedly successful | toxic applied to the intended proxy and interval | test fault setup |
| Business object changed but name/status differs | baseline object and namespace reset | test/data isolation |
| First probe fails after removal | whether recovery uses a deadline and new connection | expected transient recovery |
| Recovery exceeds budget | service restart time, network path, probe timeout | recovery failure |
| Cleanup reports toxic still present | Toxiproxy control API and `finally` removal | infrastructure/test leak |
| Appium session remains | `GET /sessions` and driver teardown | automation leak |
| ADB reverse remains | `adb -s <udid> reverse --list` | test environment leak |

Do not convert an unavailable device or provider into `PASS`. Record it as
`NOT RUN`, `BLOCKED`, or `DEFERRED`.

## Toxiproxy Checks / Toxiproxy 检查

```powershell
Invoke-RestMethod http://127.0.0.1:18474/proxies |
  ConvertTo-Json -Depth 8
```

The Week 24 API fixture uses:

```text
proxy name: qa-week24-<worker>
listen:     0.0.0.0:18100-18103
upstream:   api:8000
```

The fixture deletes the proxy after each test. If an interrupted run leaves a
proxy behind, remove only the matching `qa-week24-*` proxy after confirming no
peer worker is active.

## Evidence / 证据

Read the JSON manifest before changing a test:

```text
artifacts/e2e/week24/<test-id>/api/recovery-result.json
```

Check in this order:

1. `failure_step`
2. `fault.expected_boundary`
3. `observed`
4. `cleanup`
5. `attempts`
6. `last_probe_error`
7. `baseline` versus `recovered`

Attach Allure/JUnit and the command that produced the run. Never paste access
tokens, passwords, full UDIDs, or provider credentials into a draft or report.

## Rate Limit Recovery / 限流恢复

`W24-API-SVC-002` exhausts one client's write budget, verifies `429` and
`Retry-After`, then polls with a valid write until the natural window expires.
The recovery budget must exceed the advertised rate-limit window. Do not delete
the Redis counter to manufacture recovery.

## Android Recovery / Android 恢复

`W24-AND-001` force-stops the fixture and relaunches it in the same Appium
session. `W24-AND-002` stops the ADB server, verifies port `5037` is closed,
restarts ADB, recreates the reverse tunnel, and builds a new Appium session on
worker ports `8300/7910`.

The first `W24-AND-002` attempt failed with `ConnectException` because the ADB
reverse tunnel was not restored. The test now recreates it before opening the
catalog and the final rerun passed. This is an automation/environment recovery
boundary, not a product defect.

## iOS Device Cloud Recovery / iOS 设备云恢复

Week 24 iOS acceptance is BrowserStack-only. The workflow builds and uploads
the fixture on macOS, then runs app termination and Appium session rebuild
checks on a real iPhone:

```powershell
gh workflow run ios-fixture-cloud.yml `
  --ref codex/week24-ios-cloud-acceptance-20261108 `
  -f acceptance_target=week24 `
  -f device_name="iPhone 15" `
  -f platform_version=17
```

Verified run: `42389853343`, BrowserStack iPhone 15 / iOS 17,
`2 passed in 74.63s`, job `SUCCESS` in `2m4s`.

This does not run local Simulator, WDA internal fault injection, or iOS API+UI
cross-layer recovery. Do not record those as passed from this workflow.

## Gate G0 / Week 23 跨层入口

The minimum real path is:

```text
API creates one isolated item
-> Android or iOS fixture reads it
-> fixture archives it
-> normal authenticated API returns archived
```

Before running a mobile recovery test, verify:

- the current fixture APK is installed, not an older build;
- `catalog-status` and `catalog-archive` exist in page source;
- ADB reverse points the device API base URL to the test SUT;
- API and UI use the same fixture session and item;
- final namespace count is zero.

An old fixture APK missing the Week 23 accessibility identifiers is an
environment/build issue, not a product recovery defect.

## Cleanup / 清理

```powershell
Invoke-RestMethod http://127.0.0.1:4723/sessions | ConvertTo-Json
adb -s emulator-5554 reverse --list
docker exec quality-engineering-lab-postgres-1 psql -U qa -d qa `
  -tAc "SELECT count(*) FROM workspaces WHERE slug LIKE 'qa-ns-%';"
```

Expected for a clean run:

```text
Appium sessions: []
ADB reverse: no output
test namespaces: 0
Toxiproxy qa-week24-*: none
```
