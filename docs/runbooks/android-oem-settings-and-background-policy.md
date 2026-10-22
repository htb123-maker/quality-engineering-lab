# Android OEM Settings, Notifications, and Background Policy

## Purpose

Verify vendor-specific Android settings without assuming that AOSP package
names, resource IDs, or process-killing behavior apply to every device.

The Week 16 HyperOS acceptance covers:

- application information and package version;
- notification permission and channel settings;
- the vendor power-saving policy entries;
- observable background behavior after selecting a restrictive policy.

## Observed Environment

```text
Device: Redmi K50 / 22041211AC
Android: 14 / SDK 34
Surface: HyperOS
Fixture: com.example.qaweek15
```

## Package and Activity Ownership

Do not assume every settings screen belongs to `com.android.settings`.

| Screen | Observed component |
| --- | --- |
| Application information | `com.miui.securitycenter/com.miui.appmanager.ApplicationsDetailsActivity` |
| Notification filter | `com.android.settings/com.android.settings.Settings$NotificationFilterActivity` |
| Notification channel | `com.android.settings/com.android.settings.SubSettings` |
| Battery usage and power policy | `com.miui.securitycenter/com.miui.powercenter.legacypowerrank.PowerDetailActivity` |

Open application information deterministically:

```powershell
$serial = "<android-serial>"
adb -s $serial shell am start -W `
  -a android.settings.APPLICATION_DETAILS_SETTINGS `
  -d package:com.example.qaweek15
```

Record the actual foreground component:

```powershell
adb -s $serial shell dumpsys window |
  Select-String -Pattern "mCurrentFocus"
```

## Notification Channel Checks

The fixture creates:

```text
channelId=qa-week15-status
channelName=QA fixture status
importance=DEFAULT / 3
description=Controlled notifications for Android UI testing
```

Verify the live system channel and notification record:

```powershell
adb -s $serial shell dumpsys notification --noredact |
  Select-String -Pattern "qa-week15-status|QA fixture status" -Context 0,2

adb -s $serial shell cmd notification list |
  Select-String -Pattern "com.example.qaweek15"
```

HyperOS notification management exposes:

- Allow notifications
- Focused notifications
- Badges
- Floating notifications
- Lock-screen notifications
- Sound
- Vibration
- Persistent notifications
- Per-channel notification categories

The app-level toggle and channel-level toggle are different controls. Record
both instead of treating one as proof of the other.

## HyperOS Power Policies

The fixture's battery entry exposes these options:

| Option | Meaning |
| --- | --- |
| No restrictions | The system does not apply this vendor policy |
| Smart background restriction | System decides based on app state and resources |
| Close after 10 minutes in background | Time-based restriction |
| Prohibit background running | Restrictive vendor policy |

Read the checked option from the UI hierarchy:

```powershell
adb -s $serial shell uiautomator dump /sdcard/power-policy.xml
adb -s $serial pull /sdcard/power-policy.xml
Select-String -Path power-policy.xml -Pattern "checked=\"true\"|禁止后台运行"
```

## Background Behavior Probe

Do not use `$PID` as a custom PowerShell variable. `$PID` is a read-only
automatic variable containing the current PowerShell process ID.

Use an explicit variable name:

```powershell
$appPid = (
  adb -s $serial shell pidof com.example.qaweek15 2>$null | Out-String
).Trim()

$appPid
adb -s $serial shell input keyevent 3
Start-Sleep -Seconds 30

$appPidAfter = (
  adb -s $serial shell pidof com.example.qaweek15 2>$null | Out-String
).Trim()

$appPidAfter
adb -s $serial shell am start -W -n com.example.qaweek15/.MainActivity
```

`LaunchState: HOT` means the existing task and process were reused.
`LaunchState: COLD` usually means the old process was no longer available.

## Week 16 Observation

After selecting **Prohibit background running**:

- The UI persisted `checked=true` for that option.
- The app remained alive after 42 seconds in the background.
- The app remained alive after an additional 30 seconds with the screen off.
- Reopening the fixture returned `LaunchState: HOT` and the same PID.

Conclusion: on this HyperOS build, **Prohibit background running does not mean
synchronous process termination**. A test must not assert immediate process
death merely because the policy is selected.

Possible reasons for later termination include longer vendor grace periods,
screen and power state, resource pressure, recent-task state, or additional OEM
policy. Those conditions require separate evidence.

Restore the original policy after the experiment. The Week 16 baseline was
**Smart background restriction**.

## Acceptance Exit Criteria

- Application information shows the expected label and version.
- The foreground package/Activity is recorded rather than assumed.
- Notification permission and the `qa-week15-status` channel are visible.
- The channel name and importance match system notification dumps.
- The vendor power-policy options are recorded with the selected option.
- Background behavior is measured with PID and launch-state evidence.
- The original power policy is restored.
- No conclusion claims immediate process death without observed evidence.
