# Android Process Death and Appium Session Recovery

## Purpose

Verify what happens when the target Android application process is killed while
an Appium UiAutomator2 session is active.

The acceptance distinguishes:

```text
Activity restart
!= process death
!= UiAutomator2 session death
!= ADB device loss
```

These are separate lifecycles. A test must record which one changed.

## Prerequisites

- A fixture APK is installed on the selected device.
- `adb` is available through `ANDROID_HOME` or `PATH`.
- Appium is ready on the project endpoint.
- The device is connected by USB or wireless ADB and reports `state=device`.

Start Appium through the project script:

```powershell
.\scripts\start_appium.ps1 -Port 4723 -WaitSeconds 60
```

## Run the Recovery Probe

```powershell
.\.venv\Scripts\python.exe scripts\verify_android_process_recovery.py `
  --serial "<android-serial>" `
  --json-output artifacts\android-recovery\process-recovery.json
```

The script:

1. Force-stops the fixture and records a COLD launch.
2. Creates the first Appium session and records its PID.
3. Force-stops the package.
4. Waits until the PID disappears.
5. Queries the old session and app state.
6. Uses the old session to start the fixture again.
7. Force-stops and records another COLD launch.
8. Creates a second session and verifies package and Activity.
9. Quits both sessions.

## Expected Evidence

A successful probe returns `passed=true` and includes:

| Field | Meaning |
| --- | --- |
| `pid_before_kill` | Fixture PID while the old session was active |
| `pid_after_kill` | Empty string proves the process disappeared |
| `cold_launch` | First post-death ADB launch state |
| `old_session_probe` | Whether the old UiAutomator2 session still answers |
| `old_session_package` | Actual foreground package after target process death |
| `old_app_state` | Appium app state: `1` means not running |
| `old_session_recovery` | Whether the old session can relaunch the fixture |
| `new_session_id` | A fresh session after the death experiment |
| `recovered_package` | Package observed through the new session |
| `recovered_activity` | Activity observed through the new session |

## Week 16 Observation

On Redmi K50 / Android 14 / HyperOS:

```text
pid before kill: 13229
pid after kill: empty
old app state: 1 / NOT_RUNNING
old session probe: passed
old foreground: settings PowerDetailActivity
old session relaunch: passed
new session recovery: passed
```

Conclusion:

- `am force-stop` really ended the target App process.
- The Appium UiAutomator2 session remained alive because its automation server
  did not depend on the target App process.
- After process death, foreground state fell back to another system task.
- The old session could start the fixture again.
- A new session also recovered cleanly.

Do not assert that process death must invalidate the Appium session. That
assumption is false for this stack.

## Distinguish Kill Commands

| Command | Use | Important boundary |
| --- | --- | --- |
| `am force-stop PACKAGE` | Deterministic process-stop experiment | Also marks the package stopped |
| `am kill PACKAGE` | Kill a background process | Cannot reliably kill a foreground process |
| HOME | Move task to background | Does not prove process death |
| Restart Activity | Recreate UI state | Does not prove process death |

Use `am force-stop` when the acceptance target is explicitly process death.

## Background Soft Kill

`am kill` only targets eligible background processes. Verify the launcher is
foreground before issuing it:

```powershell
.\.venv\Scripts\python.exe scripts\verify_android_process_recovery.py `
  --serial "<android-serial>" `
  --kill-strategy am-kill `
  --json-output artifacts\android-recovery\soft-kill-recovery.json
```

Week 16 observation:

```text
PID before: 4353
launcher foreground before kill
PID after: empty
old app state: 1 / NOT_RUNNING
old session foreground: com.miui.home / .launcher.Launcher
old session relaunch: passed
new session recovery: passed
```

This confirms that a soft-killed background App and a force-stopped App share
the same important boundary: the target process is gone, but UiAutomator2 can
remain alive.

## Failure Triage

| Evidence | Meaning |
| --- | --- |
| PID still exists | Force-stop did not complete or package name is wrong |
| PID disappears but old session fails | Session lifecycle is coupled or server died |
| PID disappears and old session works | Separate automation-server lifecycle |
| Old session foreground is launcher/settings | Target task was removed |
| Old session relaunch fails | Record the exact Appium exception |
| New session fails | Repair Appium/device/server before retesting App recovery |

## Cleanup

Confirm no sessions remain:

```powershell
Invoke-RestMethod http://127.0.0.1:4723/sessions
```

Expected:

```json
{"value":[]}
```

The fixture should return to `Ready` with `Resume count: 1`, confirming a clean
process start rather than reuse of an existing Activity.
