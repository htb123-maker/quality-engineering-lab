# Android Permissions and Recovery Triage

## Purpose

Classify failures in Android permission dialogs, WebView contexts, device files,
deep links, and foreground recovery before changing waits or test assertions.

## First Snapshot

```powershell
adb devices -l
adb -s emulator-5554 shell dumpsys activity activities |
  Select-String -Pattern "topResumedActivity"
Invoke-RestMethod -Uri http://127.0.0.1:4723/status
```

Capture the pytest node ID, current package and Activity, Appium session ID,
first failing command, and relevant Appium log section.

## Fixture Preflight

The Week 15 fixture is required for runtime permission and controlled Hybrid
tests.

```powershell
.\apps\android-fixture\build.ps1 -Serial emulator-5554
adb -s emulator-5554 shell pm path com.example.qaweek15
```

Expected package path output starts with:

```text
package:
```

The APK and debug keystore remain under `artifacts/android-fixture/`.

## Permission Dialog Did Not Appear

Check these in order:

1. Confirm the test App is in the foreground.
2. Confirm the permission was revoked before tapping the request control.
3. Confirm the manifest requests the permission.
4. Confirm the request is for a runtime permission, not an install permission.
5. Confirm `com.android.permissioncontroller` owns the foreground Activity.

Useful commands:

```powershell
adb -s emulator-5554 shell dumpsys package com.example.qaweek15 |
  Select-String -Pattern "android.permission.CAMERA" -Context 0,1
adb -s emulator-5554 shell dumpsys activity activities |
  Select-String -Pattern "GrantPermissionsActivity"
```

A previously granted permission normally does not show a new prompt. A denied
permission can also be affected by Android's rationale and "don't ask again"
state; reset that state by reinstalling the fixture, not by guessing with a
longer wait.

## Permission Command Failed

`AndroidPermissions` requires full names such as
`android.permission.CAMERA`. The UiAutomator2 query type is one of `granted`,
`denied`, or `requested`, not `runtime`.

If grant or revoke returns without the expected readback state:

- verify the package owns the requested permission;
- check whether the permission is system-fixed;
- check the `User 0` permission block in `dumpsys package`;
- restore the original state after the test.

## WebView Context Failed

Error:

```text
No Chromedriver found that can automate Chrome ...
```

Restart Appium through the project script so the supported local feature is
enabled:

```powershell
.\scripts\start_appium.ps1 -Port 4723 -WaitSeconds 60
```

The script passes:

```text
--allow-insecure chromedriver_autodownload
```

This is a local test capability, not a production server setting.

Error:

```text
please close 'org.chromium.webview_shell' and try again
```

The context list contains a stale WebView owned by another foreground or cached
app. Close that process or select the exact package context:

```text
WEBVIEW_com.example.qaweek15
```

Do not select the first `WEBVIEW_` context by prefix alone when multiple
applications are installed.

## File or Clipboard Failure

- Device paths must be absolute, for example `/sdcard/Download/...`.
- Use a unique file name and delete it in `finally`.
- Verify `/sdcard` is writable on the test device.
- Restore the previous clipboard text after the assertion.
- Do not place secrets or production data in device files or clipboard tests.

## Deep Link or Recovery Failure

Check:

1. The URI and component belong to the same test App.
2. The Activity is exported when launched externally.
3. The intent action matches the manifest filter.
4. The current package and Activity are read after the launch command returns.
5. HOME reaches the configured launcher package.

`AndroidActivityTimeout` reports the expected target and the actual foreground
package/Activity. Use that evidence before increasing the timeout.

## Focused Verification

```powershell
$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp-pytest"
.\.venv\Scripts\python.exe -m pytest tests\android\test_system_interactions.py -q `
  -p no:cacheprovider
```

Expected:

```text
4 passed
```

## Exit Criteria

- The permission dialog is observed through `permissioncontroller` and the
  original permission state is restored.
- Hybrid actions run in the exact WebView context and return to `NATIVE_APP`.
- Device files and clipboard values are restored or removed.
- Deep-link and recovery assertions identify the foreground package and
  Activity.
- Environment failures remain explicit skips, never passes.
