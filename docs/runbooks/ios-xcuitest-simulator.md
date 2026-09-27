# iOS XCUITest Simulator Runbook

## Purpose

Run the first iOS Appium session without changing application code or using
production credentials. XCUITest builds and controls WebDriverAgent (WDA) on a
macOS host.

## Execution Options

| Option | Use when | Project boundary |
| --- | --- | --- |
| Local Mac + Xcode Simulator | First implementation and debugging | Preferred Day 4 path |
| macOS CI runner | Repeatable checks after local pass | Manual workflow or protected branch |
| Device cloud | No Mac and no macOS CI available | Requires provider-specific Appium endpoint and secret injection |

Pure Windows can install the XCUITest Driver package but cannot build WDA,
start an iOS Simulator, or create a real XCUITest session.

## Compatible Versions

- Appium 2.19.0
- XCUITest Driver 8.4.3 (`appium ^2.5.4`)
- Python 3.12 through `uv`
- Xcode and an installed iOS Simulator runtime

Do not install the latest XCUITest Driver without checking its Appium peer
dependency. Newer major versions may require Appium 3.

## Prepare macOS

Install Xcode, open it once, and install at least one iOS Simulator runtime.

```bash
xcode-select -p
xcrun simctl list runtimes
xcrun simctl list devices available
```

Install project and Appium dependencies:

```bash
cd "/path/to/Appium 2 study"
uv sync --frozen
npm install --global appium@2.19.0
appium driver install xcuitest@8.4.3
```

Configure the simulator selected for the session:

```bash
export QA_IOS_DEVICE_NAME="iPhone 16"
export QA_IOS_PLATFORM_VERSION="18.5"
export QA_IOS_BUNDLE_ID="com.apple.Preferences"
export QA_IOS_WDA_LOCAL_PORT="8100"
export QA_IOS_USE_NEW_WDA="true"
export QA_IOS_WDA_LAUNCH_TIMEOUT_MS="240000"
export QA_IOS_WDA_STARTUP_RETRIES="2"
export QA_IOS_WDA_STARTUP_RETRY_INTERVAL_MS="10000"
```

Set `QA_IOS_UDID` when more than one matching Simulator exists. Leave
`QA_IOS_PLATFORM_VERSION` unset when Appium should select the available runtime.
The WDA timeout values allow the first hosted-runner build to finish before
Appium marks the session as failed.

## Preflight

Run the read-only environment check. `--doctor` is slower and validates Xcode
and WDA prerequisites in more detail.

```bash
uv run --no-sync python scripts/check_ios_environment.py --doctor
```

Expected final line:

```text
iOS environment ready: True
```

## Run the Session

Boot the selected Simulator:

```bash
xcrun simctl boot "$QA_IOS_UDID"
open -a Simulator
```

Start Appium in a second terminal:

```bash
appium --address 127.0.0.1 --port 4723 --log-level debug
```

Run the smoke test:

```bash
uv run --no-sync pytest tests/ios -q \
  --alluredir=artifacts/allure-results
```

Expected result:

```text
1 passed
```

On Windows, the same test reports `1 skipped` because XCUITest requires macOS.

## Evidence

- Appium `/status` response with `ready=true`
- `xcrun simctl list devices available`
- Appium server log containing `POST /session 200`
- WDA build and `WebDriverAgentRunner` launch log
- pytest result and `artifacts/allure-results`

## Failure Triage

| Symptom | First check | Likely boundary |
| --- | --- | --- |
| `xcode-select: error` | `xcode-select -p` | Xcode command-line tools |
| No matching Simulator | `xcrun simctl list devices available` | Device name or runtime |
| WDA build failed | Appium debug log and Xcode command output | Xcode, signing, or derived data |
| `ECONNREFUSED` | Appium `/status` | Appium server not started |
| Session timeout | Simulator boot state and WDA port | Simulator, WDA, or port conflict |
| App not launched | `QA_IOS_BUNDLE_ID` | Bundle identifier or app installation |

Do not treat a WDA build failure as a pytest assertion failure. Keep the Appium,
Xcode, WDA, and Simulator logs as one diagnostic bundle.

## Device Cloud Boundary

For a device cloud, keep the same `create_ios_driver` contract and override the
Appium endpoint. Provider credentials must come from a secret store, never from
`.env.example`, source code, Allure attachments, or logs.

Provider-specific capabilities such as access keys, project names, and app IDs
belong in a future adapter. They must not leak into business tests.
