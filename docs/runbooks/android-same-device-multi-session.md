# Android Same-Device Multi-Session Port Isolation

## Purpose

Run two Appium sessions against the same Android device while isolating the
UiAutomator2 server and MJPEG forwarding ports.

This is different from running two sessions on two devices. The App state is
shared, so use read-only commands for concurrent acceptance.

## Required Ports

| Purpose | Primary | Secondary |
| --- | --- | --- |
| Appium HTTP | `4723` | `4724` |
| UiAutomator2 `systemPort` | `8200` | `8201` |
| `mjpegServerPort` | `7810` | `7811` |

The Appium HTTP ports belong to the Windows host. The UiAutomator2 system port
is used on the Android device and must also be unique for the same device.

## Physical Device Variant

Replace `emulator-5554` with the current USB or wireless ADB serial:

```powershell
adb devices -l

.\.venv\Scripts\python.exe `
  scripts\verify_android_same_device_ports.py `
  --serial "<physical-serial>" `
  --json-output artifacts\android-same-device-ports\physical.json
```

Keep both Appium servers on the same Windows host for this case. Reconnect the
phone before starting if its wireless-debugging port changed.

## Start the AVD and Servers

```powershell
emulator -avd Pixel_API_35_AOSP_ATD `
  -no-snapshot-save `
  -no-boot-anim `
  -no-audio

.\scripts\wait_for_android_ready.ps1 `
  -Serial emulator-5554 `
  -TimeoutSeconds 300

.\apps\android-fixture\build.ps1 -Serial emulator-5554

.\scripts\start_appium.ps1 -Port 4723 -WaitSeconds 60
.\scripts\start_appium.ps1 -Port 4724 -WaitSeconds 60
```

## Run the Probe

```powershell
.\.venv\Scripts\python.exe `
  scripts\verify_android_same_device_ports.py `
  --serial emulator-5554 `
  --primary-url http://127.0.0.1:4723 `
  --secondary-url http://127.0.0.1:4724 `
  --primary-system-port 8200 `
  --secondary-system-port 8201 `
  --primary-mjpeg-port 7810 `
  --secondary-mjpeg-port 7811 `
  --json-output artifacts\android-same-device-ports\same-device-ports.json
```

The probe creates both sessions concurrently and performs only read operations:

- session creation;
- UDID capability check;
- package and Activity query.

Do not concurrently mutate the same fixture state and call the result
isolation. Both sessions see the same App process and the same UI state.

## Week 16 Observation

```text
shared device: emulator-5554

primary:
  Appium: 127.0.0.1:4723
  session: 6b7bc85b-...
  systemPort: 8200
  mjpegServerPort: 7810

secondary:
  Appium: 127.0.0.1:4724
  session: 485b341d-...
  systemPort: 8201
  mjpegServerPort: 7811

both status: passed
both package: com.example.qaweek15
both Activity: .MainActivity
both remaining sessions after cleanup: []
```

Both Appium logs contained the corresponding `POST /session` request with the
expected unique service ports.

## Failure Triage

| Evidence | Likely boundary |
| --- | --- |
| Second session cannot start | Duplicate `systemPort` or `mjpegServerPort` |
| Both sessions report the same port | Settings not mapped to capabilities |
| One Appium log missing | Port-specific logging or server startup problem |
| Package changes unexpectedly | Both sessions are mutating shared App state |
| Session cleanup fails | Inspect both Appium `/sessions` endpoints |

## Boundaries

This probe covers one AVD shared by two local Appium servers. It does not cover:

- two physical devices;
- two hosts;
- device-cloud sessions;
- process-level isolation of App state on one device;
- CI-managed emulator pools.
