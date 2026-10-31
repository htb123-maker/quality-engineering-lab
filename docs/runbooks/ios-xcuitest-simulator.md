# iOS XCUITest Simulator and Device Environment Runbook

## macOS CI WDA Startup Budget

The GitHub-hosted macOS Simulator job performs a cold WDA build. A 240-second
WDA launch timeout can be shorter than the first `xcodebuild` cycle on a busy
runner, and retries can then exhaust the outer pytest timeout before the
second WDA attempt has a chance to answer `/status`.

For the Week 17 Simulator acceptance path:

- keep `QA_IOS_SHOW_XCODE_LOG=true` so `xcodebuild` failures are captured;
- use `QA_IOS_WDA_LAUNCH_TIMEOUT_MS=600000` for the cold build;
- use `QA_IOS_WDA_STARTUP_RETRIES=1` so one attempt gets a full diagnostic
  window instead of spending the budget on repeated partial builds;
- allow the pytest session smoke at least 900 seconds.

If WDA still does not answer `/status`, classify it as an XCUITest/WDA runtime
failure, not as a passed iOS environment. Preserve `ios-environment.json`,
`appium-ios.log`, the GitHub Run URL, and Allure results.

## Purpose

Prepare a macOS host for the first iOS Appium session, prove that Xcode,
Simulator, Appium, XCUITest Driver, and WebDriverAgent (WDA) can work together,
and preserve enough evidence to separate host, WDA, app, and test failures.

This runbook does not use production credentials or modify application code.

## Execution Options

| Option | Use when | Project boundary |
| --- | --- | --- |
| Local Mac + Xcode Simulator | First implementation and debugging | Preferred Week 17 path |
| macOS CI runner | Repeatable checks after a local pass | `ios-smoke.yml` |
| Device cloud | No local or CI macOS host is available | Provider adapter is still future work |

Pure Windows can install the Appium XCUITest Driver package and validate Python
capabilities. It cannot build WDA, boot an iOS Simulator, sign a real-device WDA,
or create a real XCUITest session.

## Compatible Versions

| Component | Week 17 baseline | Why it matters |
| --- | --- | --- |
| Appium | 2.19.0 | Server and Driver peer dependency |
| XCUITest Driver | 8.4.3 | Builds and launches WDA |
| Python | 3.12 through `uv` | Project runtime |
| Xcode | Installed and selected | Provides `xcodebuild`, Simulator, and XCTest |
| iOS runtime | At least one available Simulator runtime | Device target |

Do not install the latest XCUITest Driver without checking its Appium peer
dependency. A newer major version may require Appium 3.

## 1. Prepare macOS

Install Xcode, open it once, accept the license, and install at least one iOS
Simulator runtime.

```bash
xcode-select -p
xcodebuild -version
xcrun simctl list runtimes
xcrun simctl list devices available
```

If `xcode-select -p` points at the wrong location:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
```

Install the project and Appium dependencies:

```bash
cd "/path/to/Appium 2 study"
uv sync --frozen
npm install --global appium@2.19.0
appium driver install xcuitest@8.4.3
```

`xcodebuild -version` is also a license check. If it reports that the license
has not been accepted, open Xcode or run the command it requests as an
administrator. Do not treat a license failure as an Appium test failure.

## 2. Configure the Simulator Path

Use a real installed runtime. The values below are an example, not a guarantee
that `iOS 18.5` and `iPhone 16` exist on the host.

```bash
export QA_IOS_DEVICE_NAME="iPhone 16"
export QA_IOS_PLATFORM_VERSION="18.5"
export QA_IOS_UDID=""
export QA_IOS_BUNDLE_ID="com.apple.Preferences"
export QA_IOS_WDA_LOCAL_PORT="8100"
export QA_IOS_USE_NEW_WDA="true"
export QA_IOS_WDA_LAUNCH_TIMEOUT_MS="240000"
export QA_IOS_WDA_STARTUP_RETRIES="2"
export QA_IOS_WDA_STARTUP_RETRY_INTERVAL_MS="10000"
```

Leave `QA_IOS_PLATFORM_VERSION` unset when Appium should select the newest
matching runtime. Set `QA_IOS_UDID` when several Simulators have the same name.
The UDID is authoritative over the display name.

The WDA timeouts budget time for the first `xcodebuild` and
`WebDriverAgentRunner` launch. They do not repair a broken Xcode installation.

## 3. Run the Preflight

The preflight is read-only unless `--output` is supplied. It checks macOS,
Xcode, iOS runtimes, a matching Simulator, Appium, and the XCUITest Driver.

```bash
uv run --no-sync python scripts/check_ios_environment.py \
  --profile simulator
```

Expected final line:

```text
iOS simulator environment ready: True
```

Write machine-readable evidence:

```bash
mkdir -p artifacts
uv run --no-sync python scripts/check_ios_environment.py \
  --profile simulator \
  --json \
  --output artifacts/ios-environment.json
```

Check a running Appium server as part of the same evidence:

```bash
uv run --no-sync python scripts/check_ios_environment.py \
  --profile simulator \
  --server-url http://127.0.0.1:4723 \
  --json \
  --output artifacts/ios-environment.json
```

`--doctor` runs the slower Appium XCUITest doctor. Use it while debugging Xcode
or WDA prerequisites, not as a mandatory step in every smoke run:

```bash
uv run --no-sync python scripts/check_ios_environment.py \
  --profile simulator \
  --doctor
```

On Windows, the command must fail with missing macOS/Xcode checks. That failure
is the correct platform boundary, not a reason to mark the iOS suite as passed.

## 4. Boot the Simulator

Select an available UDID without manually copying it from a large inventory:

```bash
xcrun simctl list devices available -j |
  python3 scripts/select_ios_simulator.py \
    --device-name "${QA_IOS_DEVICE_NAME:-iPhone 16}" \
    --fallback-prefix iPhone
```

Export the selected UDID, then boot and wait for the device:

```bash
export QA_IOS_UDID="<selected-udid>"
xcrun simctl boot "$QA_IOS_UDID" || true
xcrun simctl bootstatus "$QA_IOS_UDID" -b
open -a Simulator
```

`|| true` is intentional for an already-booted device. The following
`bootstatus -b` is still required because issuing `boot` does not prove that
SpringBoard is ready.

## 5. Start Appium and Run the Smoke

In a second terminal:

```bash
appium --address 127.0.0.1 --port 4723 --log-level debug
```

Confirm readiness:

```bash
curl --fail --silent http://127.0.0.1:4723/status
```

Run the project smoke:

```bash
uv run --no-sync pytest tests/ios -q \
  --alluredir=artifacts/allure-results
```

Expected result:

```text
1 passed
```

The first run may be significantly slower because Appium builds and installs
WDA. A later successful session does not prove the first-build path is healthy;
retain the first WDA build log when validating a new Xcode version.

## 6. Real-Device Path

Real-device WDA requires Apple signing before Appium can launch the runner.
Complete these manual prerequisites:

1. Sign in to Xcode with an Apple Developer account.
2. Select the correct Team for the WDA project.
3. Create or download a valid Apple Development certificate.
4. Connect and unlock the iPhone, then trust the computer.
5. Enable Developer Mode on the device if the iOS version requires it.
6. Confirm the target app is installed and its bundle identifier is correct.

Check the local signing inventory without exporting certificate material:

```bash
security find-identity -v -p codesigning
uv run --no-sync python scripts/check_ios_environment.py --profile device
```

The preflight can prove that at least one code-signing identity exists and that
Xcode can see a physical iPhone or iPad. It cannot prove that the Apple account
owns the target app, that the device is trusted, or that the provisioning
profile matches the bundle identifier.

Do not put Apple account passwords, private keys, provisioning profiles, or
session secrets in environment examples, Allure attachments, or repository
files.

## 7. macOS CI

The `iOS Appium Smoke` workflow is manual:

```bash
gh workflow run ios-smoke.yml \
  --ref study/week-17-ios-environment-wda
gh run list --workflow ios-smoke.yml --limit 1
gh run watch <run-id> --exit-status
```

The workflow selects and boots a Simulator, installs Appium and XCUITest Driver,
starts Appium, writes `artifacts/ios-environment.json`, runs `tests/ios`, and
uploads the diagnostic bundle.

The workflow success is the macOS execution evidence. A Windows `1 skipped`
result is not a pass.

## 8. Evidence Bundle

Keep these files together for a successful or failed session:

- `artifacts/ios-environment.json`
- `xcrun simctl list devices available -j`
- Appium `/status` response
- Appium server log with `POST /session`
- Xcode or `xcodebuild` output
- WDA build and `WebDriverAgentRunner` launch log
- pytest output and `artifacts/allure-results`
- screenshots, page source, and device logs for failures

The bundle must identify one host, one Xcode version, one Simulator or device,
one Appium version, one XCUITest Driver version, and one tested app.

## 9. Failure Triage

| Symptom | First check | Likely boundary |
| --- | --- | --- |
| `xcode-select: error` | `xcode-select -p` | Xcode command-line selection |
| `xcodebuild` license error | `xcodebuild -version` | Xcode first-run/license setup |
| No matching Simulator | `xcrun simctl list devices available` | Runtime, device name, or UDID |
| Simulator stays `Shutdown` | `xcrun simctl bootstatus "$QA_IOS_UDID" -b` | Simulator boot |
| `ECONNREFUSED` | Appium `/status` | Appium server not running |
| XCUITest Driver missing | `appium driver list --installed --json` | Driver installation |
| WDA build failed | Appium debug log and Xcode build output | Xcode, WDA, or DerivedData |
| WDA launch timed out | Simulator state, WDA port, launch timeout | WDA startup or port conflict |
| Real-device WDA signing failed | `security find-identity` and Xcode Team | Certificate or provisioning |
| App not launched | `QA_IOS_BUNDLE_ID` | App installation or bundle identifier |

Do not turn a WDA build or signing failure into a pytest assertion failure.
Classify the failure at the boundary where it occurred and preserve the full
diagnostic bundle.

## 10. Device-Cloud Boundary

A device cloud may expose an Appium-compatible WebDriver endpoint, but
provider-specific credentials and capabilities must not enter business tests.
Keep the existing `create_ios_driver` contract and add a provider adapter only
when the project has a real account and a pinned endpoint.

Provider secrets belong in a secret store. They must not appear in
`.env.example`, source code, logs, screenshots, Allure results, or Git history.
