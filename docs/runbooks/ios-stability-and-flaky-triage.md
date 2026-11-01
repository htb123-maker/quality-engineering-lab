# iOS Stability and Flaky Triage

## Trigger

Use this runbook when any of the following occurs:

- the Week 21 inventory count or mapping fails;
- a repeated iOS test changes between pass and fail;
- the dual-Simulator verifier rejects device, port, or DerivedData uniqueness;
- the current-major suite leaves an Appium session or Simulator process;
- the previous-major job is blocked by a missing runtime;
- BrowserStack returns `NATIVE_APP` only for the WebView case.

## First Checks

```powershell
uv run python scripts/check_ios_test_inventory.py --json
uv run pytest tests/ios --collect-only -q
```

Do not change the expected count or remove mapping checks to make these commands
pass. The inventory must map source functions one to one.

On macOS:

```bash
xcrun simctl list devices available -j
xcrun xcodebuild -version
curl --fail --silent http://127.0.0.1:4723/status
curl --fail --silent http://127.0.0.1:4723/sessions
```

## Failure Triage Order

1. Read the first failure, not a later retry.
2. Open `failure.failure.json`.
3. Check `failure_type`, but verify it against screenshot and page source.
4. Confirm the test used the intended device ID, runtime, Appium port, WDA port,
   and DerivedData.
5. For session or WDA failures, classify as `ENVIRONMENT` until evidence shows a
   product defect.
6. For locator timeout, compare the page source with the locator and wait state.
7. For a pass/fail change, compare the first outcome and environment across the
   affected JUnit reports.
8. Only after evidence is complete, propose product, test, data, device, network,
   or environment ownership.

## Evidence Fields

```text
test_id
captured_at
failure_type
error_type
error_message
screenshot
page_source
provider
device_name
platform_version
bundle_id
appium_server_url
run_id
```

UDIDs and credential-like fields are redacted. Do not add an unmasked session
payload or Appium command log to a defect draft.

## Flaky Decision

A test is a flaky candidate only when the same node ID both passes and fails
under comparable conditions. A skipped test is not flaky. A test that fails every
run is a persistent failure, not flaky.

Do not:

- replace first outcomes with a retry result;
- add a global retry plugin to hide the signal;
- quarantine a test before recording the failure and environment;
- count xfailed or skipped tests as passed.

Use `artifacts/ios-week21/stability.json` as the source for pass rate, flaky
candidates, and p50/p95 durations.

## Version Matrix

When `previous-major.json` says `BLOCKED`:

- report the runtime as `BLOCKED`, not `PASS`;
- keep the current-major evidence;
- do not install an uncontrolled large runtime just to obtain a green result;
- when a compatible runtime becomes available, execute the risk-based subset
  and replace `BLOCKED` only with actual results.

## WebView Limitation

Week 19 already recorded BrowserStack iPhone 15 / iOS 17 exposing only
`NATIVE_APP` after a 70-second wait. Keep the WebView case strict `xfail` until
the provider or fixture exposes a usable context. Native-content and hierarchy
checks remain valid evidence and do not become a WebView-context pass.

## Session Leak

After the suite and stability runs:

```bash
curl --fail --silent http://127.0.0.1:4723/sessions
```

The `value` array must be empty. If not, save the response, Appium log tail,
worker ID, device ID, and last test node before restarting Appium. Do not discard
the original process state as the first response.
