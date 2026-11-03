# iOS WDA Build and Signing Triage

## Purpose

Separate WebDriverAgent (WDA) failures into host, Xcode, Simulator, app,
signing, port, and session layers. XCUITest cannot create a valid session until
WDA builds, launches under XCTest, and becomes reachable by Appium.

Use this runbook after the broader environment preflight:

```bash
uv run --no-sync python scripts/check_ios_environment.py \
  --profile simulator \
  --server-url http://127.0.0.1:4723 \
  --doctor
```

## WDA Startup Chain

```mermaid
flowchart LR
    A[Appium request] --> B[XCUITest Driver]
    B --> C[xcodebuild]
    C --> D[Sign WDA]
    D --> E[Install WDA]
    E --> F[WebDriverAgentRunner]
    F --> G[WDA HTTP endpoint]
    G --> H[XCUITest session]
    H --> I[Target app]
```

Each arrow has its own evidence. A Python exception at the end of the chain is
usually a symptom, not the root cause. Read the Appium log from the first
failing layer instead of retrying the session without a diagnosis.

## 1. Confirm the Host and Xcode

```bash
uname -a
xcode-select -p
xcodebuild -version
xcrun simctl list runtimes
```

Required facts:

- The process is running on macOS.
- `xcode-select -p` points at the intended Developer directory.
- `xcodebuild -version` succeeds and prints an Xcode version.
- At least one iOS Simulator runtime is available.

A license, command-line selection, or missing runtime failure happens before
WDA starts. Repair it before changing Appium capabilities or Driver versions.

## 2. Confirm the Target Device

For a Simulator:

```bash
xcrun simctl list devices available
xcrun simctl bootstatus "$QA_IOS_UDID" -b
```

For a real device:

```bash
xcrun xctrace list devices
```

Keep the Simulator UDID or real-device UDID in the diagnostic record. Confirm
that `QA_IOS_UDID`, `QA_IOS_DEVICE_NAME`, and `QA_IOS_PLATFORM_VERSION` describe
the same target. A display name is not an identity.

## 3. Confirm Appium and XCUITest Driver

```bash
appium --version
appium driver list --installed --json
```

The Week 17 baseline is Appium 2.19.0 and XCUITest Driver 8.4.3. If the Driver
is missing or replaced by an incompatible version, the failure is in the Appium
installation layer.

Run the Driver doctor after the cheap checks:

```bash
appium driver doctor xcuitest
```

Keep the complete doctor output. It can be slow and may build or inspect
WDA-related prerequisites; it is a diagnostic command, not a smoke-test
retry loop.

## 4. Read the WDA Build Failure

Start Appium with debug logging:

```bash
appium --address 127.0.0.1 --port 4723 --log-level debug
```

Retain the log around:

- Driver selection
- `xcodebuild` command line
- DerivedData path
- Code-signing operation
- WDA installation
- `WebDriverAgentRunner` launch
- WDA port listen and readiness
- `POST /session` response

Locate DerivedData without deleting it:

```bash
find "$HOME/Library/Developer/Xcode/DerivedData" \
  -maxdepth 2 \
  -type d \
  -name 'WebDriverAgent-*'
```

Do not delete DerivedData as a reflex. First prove whether the failure is stale
build output, signing, a port conflict, or a device transport problem. If a
clean rebuild is justified, move one DerivedData directory to a temporary
location and preserve the previous build log.

## 5. Check Signing for a Real Device

Run:

```bash
security find-identity -v -p codesigning
uv run --no-sync python scripts/check_ios_environment.py --profile device
```

Then verify in Xcode:

1. The Apple Developer account is signed in.
2. WDA has the correct Team.
3. The Apple Development certificate is valid and not expired.
4. The device is registered for the provisioning profile.
5. The bundle identifier is unique and owned by the account.
6. The device is unlocked and trusted.
7. Developer Mode is enabled if required by the iOS version.

The preflight can count identities and confirm that Xcode sees an iPhone or
iPad. It cannot prove account ownership, profile validity, bundle ownership, or
device trust. Keep those as human acceptance criteria.

Never print or attach a private key, certificate archive, provisioning profile,
Apple password, or device-cloud access token.

## 6. Check WDA Ports and Processes

```bash
lsof -nP -iTCP:4723 -sTCP:LISTEN
lsof -nP -iTCP:8100 -sTCP:LISTEN
curl --fail --silent http://127.0.0.1:4723/status
```

The Appium port and WDA local port serve different purposes. A free WDA port
does not prove Appium is running, and a ready Appium server does not prove WDA
can bind its port.

For parallel sessions, every worker needs an isolated WDA local port. That
isolation belongs to the future Week 20 device-matrix design, not to business
test code.

## 7. Failure Classification

| Observed failure | Boundary | Evidence to collect |
| --- | --- | --- |
| `xcode-select` is wrong | Host | `xcode-select -p` |
| Xcode license rejection | Host | `xcodebuild -version` |
| No Simulator runtime | Xcode/runtime | `simctl list runtimes -j` |
| Simulator not booted | Device | `simctl bootstatus` |
| XCUITest Driver missing | Appium package | `driver list --installed --json` |
| WDA compile error | Xcode/WDA | `xcodebuild` and Appium debug log |
| Signing requirement failure | Apple signing | `security find-identity`, Xcode Team |
| Device not trusted | Device/host transport | Xcode device list and device state |
| WDA port already in use | Port | `lsof`, Appium log |
| WDA launch timeout | WDA startup | Simulator state, launch timeout, WDA log |
| Target app not found | App installation | bundle ID and `simctl listapps` |
| Session works but element missing | App/UI | page source, screenshot, locator log |

The last row is a test or app-layout problem, not a WDA environment failure.

## 8. Minimum Diagnostic Bundle

```text
host + macOS version
+ Xcode path and version
+ Simulator/device inventory
+ Appium and XCUITest Driver versions
+ ios-environment.json
+ Appium debug log
+ WDA build and launch excerpt
+ pytest and Allure results
```

Do not claim an iOS pass from a Windows skip, a static import, or a successful
Driver installation. A pass requires a real `POST /session` response and a
completed XCUITest command against the selected target.
