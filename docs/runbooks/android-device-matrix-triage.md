# Android Device Matrix Triage

## Purpose

Classify failures caused by device assignment, emulator readiness, Appium
session contention, parallel host load, or missing physical-device evidence.

## First Snapshot

```powershell
adb devices -l
Invoke-RestMethod -Uri http://127.0.0.1:4723/status
Invoke-RestMethod -Uri http://127.0.0.1:4723/sessions
Get-Content configs\android-device-matrix.yaml
```

Record:

- pytest node ID;
- xdist worker ID;
- matrix device ID and UDID;
- Appium session ID;
- current package and Activity;
- first failing Appium command.

## Worker Does Not Match a Device

Expected errors:

```text
pytest requested 2 workers but the matrix has 1 active device(s)
```

or:

```text
pytest requested 2 workers but the matrix has 3 active device(s)
```

The second case is not an error in the matrix. It means the test process was
started with too many workers for the intended run. Use:

```powershell
-n 2
```

for the two local AVDs. Never point two workers at the same UDID.

## One AVD Is Missing

```powershell
adb devices -l
D:\Android\Sdk\emulator\emulator.exe -avd Pixel_API_35_AOSP_ATD_2 `
  -port 5556 -no-window -no-audio -no-boot-anim `
  -gpu swiftshader_indirect
.\scripts\wait_for_android_ready.ps1 `
  -Serial emulator-5556 `
  -TimeoutSeconds 300
```

Do not start the pytest matrix until both required serials report `device`.

## Fixture Missing on One Device

```powershell
adb -s emulator-5554 shell pm path com.example.qaweek15
adb -s emulator-5556 shell pm path com.example.qaweek15
```

Each output must start with `package:`. Install through the runner or:

```powershell
.\apps\android-fixture\build.ps1 -Serial emulator-5554
.\apps\android-fixture\build.ps1 -Serial emulator-5556
```

## ADB Command Timed Out

Observed during the first parallel run:

```text
adb.exe ... shell dumpsys package com.example.qaweek15
timed out after 20000ms
```

The project default is now:

```text
QA_ANDROID_ADB_EXEC_TIMEOUT_MS=60000
```

Check host memory and CPU before increasing it again:

```powershell
Get-Process emulator,qemu-system-x86_64,node -ErrorAction SilentlyContinue |
  Sort-Object CPU -Descending |
  Select-Object Name,CPU,WorkingSet
```

A timeout is a failure of command completion, not proof that the assertion is
wrong. Do not add a fixed sleep or retry around the assertion.

## Session Contention

Symptoms:

- one worker sees the other app package;
- the same Activity is foreground on both devices;
- a session disappears after another worker starts;
- `socket hang up` occurs while changing context.

Check:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:4723/sessions
adb -s emulator-5554 shell dumpsys activity activities |
  Select-String -Pattern "topResumedActivity"
adb -s emulator-5556 shell dumpsys activity activities |
  Select-String -Pattern "topResumedActivity"
```

Each serial must have a distinct UDID in its Appium capabilities. After a run,
the sessions endpoint must return an empty list.

## Evidence Is Missing

The runner writes:

```text
artifacts/android-matrix/<run-id>/pytest-console.log
artifacts/android-matrix/<run-id>/allure-results/
artifacts/android-matrix/<run-id>/allure-report/
```

Open the Allure report:

```powershell
allure open artifacts\android-matrix\<run-id>\allure-report
```

Every result should include `android_device`, `android_udid`, and
`android_role`. A failing test should include screenshot, page source, and
logcat attachments.

## Physical Device Profile

Confirm the device and run the physical profile directly:

```powershell
$serial = "<device-serial>"
adb -s $serial get-state
.\scripts\run_android_matrix.ps1 -PhysicalSerial $serial -Workers 1
```

The runner reads `ro.build.version.release`, selects `physical-android`, and
records `physical-device` in Allure. Use a mixed AVD plus physical run when
parallel-device evidence is required:

```powershell
.\scripts\run_android_matrix.ps1 `
  -PrimarySerial emulator-5554 `
  -PhysicalSerial $serial `
  -Workers 2
```

Record the manufacturer, model, OS version, permission UI, and launcher package
in the report. Do not infer physical-device success from AVD results.

## Exit Criteria

- Both intended serials are `device` and fully booted.
- The fixture package exists on every selected device.
- Worker count is not greater than active device count.
- Each worker reports a distinct UDID.
- `adbExecTimeout` is explicit and the host is not saturated.
- Allure results identify the logical device and contain failure diagnostics.
- Appium has no sessions left after teardown.
