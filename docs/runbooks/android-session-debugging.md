# Android Session Debugging

## Purpose

This runbook follows one Android session from pytest through the Appium Python
Client, Appium Server, UiAutomator2 Driver, ADB, and the AVD. Use it when a
session fails before any business locator or gesture runs.

## Start the Local Chain

```powershell
Start-Process `
  -FilePath 'D:\Android\Sdk\emulator\emulator.exe' `
  -ArgumentList @(
    '-avd', 'Pixel_API_35_AOSP_ATD',
    '-no-window', '-no-audio', '-no-boot-anim', '-no-snapshot',
    '-port', '5554'
  ) `
  -WindowStyle Hidden

.\scripts\wait_for_android_ready.ps1 `
  -Serial emulator-5554 `
  -TimeoutSeconds 300

.\scripts\start_appium.ps1 -Port 4723 -WaitSeconds 60
```

`start_appium.ps1` chooses JDK 17+, writes `artifacts/appium-server.*.log`, and
waits for Appium `/status`.

## Run One Session

```powershell
$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp-pytest"
.\.venv\Scripts\python.exe -m pytest tests\android -q -p no:cacheprovider
```

The session is successful only when all of these are true:

1. ADB reports the configured UDID in state `device`.
2. Appium `/status` reports `ready=true`.
3. Appium logs `POST /session` and then `POST /session 200`.
4. pytest reports one passed test.
5. The driver executes `quit()` and the session disappears.

## PyCharm Breakpoints

Use the checked-in `Android Tests` pytest configuration.

| Breakpoint | Inspect | Why |
| --- | --- | --- |
| `build_android_options` | Every `appium:*` capability | Proves settings become the intended target device and app |
| `create_android_driver` before `Remote` | `command_executor`, options | Distinguishes endpoint errors from device errors |
| `tests/android/test_session.py` after driver creation | `session_id`, `current_package` | Proves Appium returned a real session and reached the app |
| `finally: driver.quit()` | session id before teardown | Confirms cleanup targets the expected session |

Useful conditional breakpoints:

```python
settings.android_udid != "emulator-5554"
driver.session_id is None
driver.current_package != settings.android_app_package
```

Set a breakpoint in `build_android_options`, then run Debug on `Android Tests`.
The debugger should stop before any HTTP request is sent. If it does not stop,
first verify the PyCharm Python SDK and working directory; see
`docs/runbooks/week1-environment-recovery.md`.

Appium defaults `newCommandTimeout` to 60 seconds. A debugger can easily pause
longer than that, after which Appium ends the session and later commands return
404. The Android factory therefore sets
`QA_ANDROID_NEW_COMMAND_TIMEOUT_SECONDS=300`, and the real-session smoke test
uses a 300-second pytest timeout. Pause at breakpoints for minutes, not tens of
minutes; the idle session is still expected to expire eventually.

## ADB Snapshot

Collect these before changing code:

```powershell
adb devices -l
adb -s emulator-5554 get-state
adb -s emulator-5554 shell getprop sys.boot_completed
adb -s emulator-5554 shell getprop init.svc.bootanim
adb -s emulator-5554 shell service check package
adb -s emulator-5554 shell service check settings
adb -s emulator-5554 shell pm list packages |
  Select-String 'io.appium|fakesystemapp'
adb -s emulator-5554 shell ps -A |
  Select-String 'uiautomator|io.appium'
```

Current AOSP ATD evidence:

```text
emulator-5554  device  product:sdk_slim_x86_64  model:Android_ATD_built_for_x86_64
Android 15
package:io.appium.settings
package:io.appium.uiautomator2.server
package:io.appium.uiautomator2.server.test
```

## Appium Log Sequence

Read the complete sequence, not only the final error:

```powershell
Get-Content artifacts\appium-server.out.log -Wait
```

Expected Week 13 session sequence:

```text
HTTP --> POST /session
Attempting to find matching driver for UiAutomator2 / Android
The 'uiautomator2' driver was installed and matched caps
Using device: emulator-5554
Adding io.appium.settings / uiautomator2 server packages to Doze whitelist
Starting UIAutomator2 server 7.7.1
Starting target package/activity
New AndroidUiautomator2Driver session created successfully
HTTP <-- POST /session 200
```

## Failure Boundaries

| Boundary | Fast evidence | Owning action |
| --- | --- | --- |
| Python Client import | `python -c "import appium"` | Fix project environment |
| Appium Server | `/status` or port 4723 listener | Start or restart Appium |
| Driver selection | Appium log says no matching driver | Verify `uiautomator2@4.2.9` |
| ADB transport | `adb devices -l`, `get-state` | Restart ADB/AVD |
| Android services | package/settings service checks | Wait for full boot |
| UiAutomator2 server | server package/process and log | Inspect device logcat |
| Target app | package/activity in `dumpsys package` | Fix capability or app install |
| Session teardown | `DELETE /session` and no residual session | Fix fixture cleanup |

`socket hang up` while starting UiAutomator2 can be transient during server
startup. It only becomes a failure if Appium exhausts its 30-second wait or the
final `POST /session` does not return 200.

## Exit Criteria

- One real pytest session passes.
- `POST /session 200` and normal teardown are both visible.
- The configured UDID and package/activity match the ADB snapshot.
- Any failure is assigned to a specific boundary above before code changes.
