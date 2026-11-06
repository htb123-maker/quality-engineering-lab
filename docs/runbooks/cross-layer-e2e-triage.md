# Cross-Layer E2E Triage / 跨层 E2E 排障

## Start Order

1. Start the local SUT and verify readiness.
2. Build and install the Android fixture.
3. Start the Appium server.
4. Run one Test ID before the full inventory.
5. Verify no namespace, fixture session, file, or Appium session remains.

```powershell
.\scripts\start_sut.ps1 -WaitSeconds 180
.\apps\android-fixture\build.ps1
npx appium --address 127.0.0.1 --port 4723
```

```powershell
$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp-pytest"
.\.venv\Scripts\python.exe -m pytest tests\e2e\test_catalog_cross_layer.py `
  -q -k E2E-CAT-001
```

## Failure Layers

| Symptom | First check | Boundary |
| --- | --- | --- |
| `catalog: error|ConnectException` | Emulator host URL and SUT readiness | environment/network |
| `catalog: error|IllegalStateException` | HTTP status and SUT logs | API/fixture |
| UI active but API active after archive | fixture POST response and request ID | UI/API contract |
| UI archived but API active | cache invalidation and commit | product/API |
| `fixture_session_not_found` | item deletion and session TTL | fixture/session |
| `permission_denied` | role and `can_archive` | expected authorization boundary |
| duplicate item rows | namespace cleanup and archive transaction | test/data isolation |
| Appium cannot find catalog locators | installed APK version and page source | environment/build |

## Android Host Address

The Android fixture uses an ADB reverse tunnel so the same address works for
Emulator and USB-connected devices:

```text
adb -s <udid> reverse tcp:18000 tcp:18000
http://127.0.0.1:18000
```

For a physical device over Wi-Fi without ADB reverse, use the test host LAN
address or an approved tunnel instead.

## Evidence

Read:

```text
artifacts/e2e/week23/<test-id>/android/e2e-result.json
artifacts/e2e/week23/android/
```

The mobile step may also write a screenshot, page source, and sanitized failure
manifest. Never put access tokens, passwords, or full UDIDs in UI text.

## Cleanup

- Delete the test namespace through the namespace pool.
- Delete fixture session keys with the namespace or TTL.
- Ensure `GET /sessions` on Appium returns an empty list.
- Ensure the mobile fixture file state is removed.
- Never turn a skipped or blocked device run into a passing row.
