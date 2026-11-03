# Android Wireless ADB Disconnect and Session Recovery

## Purpose

Verify what happens when the wireless ADB transport disappears while an Appium
UiAutomator2 session is active, then returns on the same device address.

This is different from:

- killing the target App process;
- pressing HOME;
- restarting an Activity;
- losing the Appium server;
- changing the wireless-debugging port.

## Run the Probe

Appium must be ready:

```powershell
.\scripts\start_appium.ps1 -Port 4723 -WaitSeconds 60
```

Run the bounded transport probe:

```powershell
.\.venv\Scripts\python.exe scripts\verify_android_transport_recovery.py `
  --serial "<wireless-adb-ip:port>" `
  --reconnect-timeout 30 `
  --json-output artifacts\android-recovery\transport-recovery.json
```

The script:

1. Starts the fixture and creates the first Appium session.
2. Records the fixture PID.
3. Runs `adb disconnect`.
4. Confirms the explicit wireless serial is no longer available.
5. Queries the old session during the outage.
6. Runs `adb connect`.
7. Waits for ADB state `device`.
8. Queries the same old session after reconnect.
9. Creates and verifies a new Appium session.
10. Reconnects defensively in `finally` and quits all sessions.

## Expected Evidence

| Field | Meaning |
| --- | --- |
| `adb_state_during_outage` | Must not be `device` |
| `old_session_during_outage` | Expected to fail while transport is absent |
| `adb_state_after_reconnect` | Must return to `device` |
| `old_session_after_reconnect` | Proves whether the same session recovers |
| `old_package_after_reconnect` | Actual foreground package after recovery |
| `new_session_id` | Fresh session creation after reconnect |
| `recovered_package` | Package observed through the new session |

## Week 16 Observation

On Redmi K50 / Android 14 / wireless ADB:

```text
serial: 172.20.10.10:<port>
PID before disconnect: 5816
outage state: error: device '<serial>' not found
old session during outage: failed
failure: Could not retrieve currently focused package and activity
state after reconnect: device
old session after reconnect: passed
old package: com.example.qaweek15
old activity: .MainActivity
new session recovery: passed
remaining Appium sessions: []
```

Conclusion:

- Losing wireless ADB breaks commands that require device access.
- The failure is explicit: `device not found`, not a false assertion failure.
- Reconnecting the same wireless serial allowed the existing Appium session to
  become usable again.
- A new session also recovered normally.

Do not treat a temporary ADB transport failure as proof that the App or the
Appium session is permanently dead.

## Failure Triage

| Observation | Meaning |
| --- | --- |
| `adb connect` fails immediately | Check Wi-Fi, IP, port, VPN, or wireless debugging state |
| Port changed | Reopen wireless debugging and use the new displayed port |
| ADB state returns but old session fails | Record exception and create a new session |
| New session also fails | Repair Appium or UiAutomator2 before retrying |
| Device cycles offline/online | Inspect Wi-Fi sleep and vendor background policies |
| Duplicate mDNS and manual serial exist | Bind tests to one explicit serial |

## Boundaries

This probe does not cover:

- rebooting the phone;
- changing Wi-Fi networks;
- turning wireless debugging off;
- losing the Appium host;
- a changed wireless-debugging port;
- simultaneous App process and ADB loss.

Those require separate acceptance cases and evidence.
