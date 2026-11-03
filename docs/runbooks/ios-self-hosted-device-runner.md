# iOS Self-Hosted Physical Device Runner

## Purpose

Run real-iPhone XCUITest sessions on a trusted self-hosted macOS runner.

The runner needs more than Appium:

- macOS and Xcode;
- an Apple Development signing identity;
- a connected, trusted iPhone;
- a runner process that can access the signing Keychain;
- repository variables for the device and signing configuration.

## Runner Registration

In GitHub, open:

```text
Repository -> Settings -> Actions -> Runners -> New self-hosted runner
```

Choose macOS and follow the generated download/configuration commands on the
Mac. Add a custom label:

```text
ios-device
```

The workflow expects:

```text
self-hosted
macOS
ios-device
```

Do not send the registration token through chat or commit it. It is temporary
and must be entered only on the Mac.

The built-in labels are case-insensitive in workflow matching, but use the same
spelling shown by GitHub.

## Runner User and Keychain

Xcode codesigning reads certificates from the runner user's Keychain. A service
runner may run as a different user and fail to find the login Keychain.

Preferred first setup:

- run the runner interactively in the logged-in Mac user session;
- verify WDA signing there;
- only then install it as a service.

Never put the Keychain password or certificate private key in the repository,
workflow YAML, variables, or Allure artifacts.

## Mac Prerequisites

```bash
xcode-select -p
xcodebuild -version
xcrun simctl list runtimes
xcrun xctrace list devices
security find-identity -v -p codesigning
```

The iPhone must be:

- connected by USB;
- unlocked and trusted by the Mac;
- registered for the Apple development team;
- running a compatible iOS version;
- using Developer Mode when required;
- visible in `xctrace list devices`.

WDA needs a valid Apple Development certificate and provisioning configuration.

## Repository Variables

Create these under:

```text
Repository -> Settings -> Secrets and variables -> Actions -> Variables
```

| Variable | Required | Example boundary |
| --- | --- | --- |
| `IOS_DEVICE_NAME` | Yes | `iPhone 15` |
| `IOS_PLATFORM_VERSION` | Optional | `18.5` |
| `IOS_DEVICE_UDID` | Yes | Physical device UDID |
| `IOS_BUNDLE_ID` | Yes | Installed target App |
| `IOS_XCODE_ORG_ID` | Yes | Apple Team ID |
| `IOS_XCODE_SIGNING_ID` | Optional | `Apple Development` |
| `IOS_UPDATED_WDA_BUNDLE_ID` | Recommended | Team-owned unique bundle ID |

Do not print private certificates, passwords, or cloud access keys.

## Workflow

After the runner is online:

```powershell
gh workflow run ios-device-smoke.yml `
  --ref study/week-17-ios-environment-wda
gh run list --workflow ios-device-smoke.yml --limit 1
gh run watch <run-id> --exit-status
```

The workflow:

1. records Xcode, signing identities, and physical-device inventory;
2. installs Appium 2.19.0 and XCUITest Driver 8.4.3;
3. starts Appium on `127.0.0.1:4723`;
4. runs the physical-device preflight;
5. runs `tests/ios`;
6. uploads environment JSON, Appium logs, and Allure results.

## Evidence to Retain

- `artifacts/ios-device-environment.json`
- `artifacts/appium-ios-device.log`
- `artifacts/allure-results/`
- Xcode version and `xcode-select -p`
- `security find-identity` summary without certificate material
- physical-device inventory
- WDA build/launch excerpt

## Device Cloud Boundary

A device cloud is a different execution path:

- provider endpoint;
- provider-specific authentication;
- provider-specific device selection capabilities;
- application upload and cleanup;
- cloud session logs.

No universal cloud adapter can be written correctly without choosing a provider.
The provider must be specified before adding secrets or capabilities.
