# Android Orientation, Locale, and RTL Verification

## Purpose

Verify that the fixture remains usable when:

- the App language changes independently of the device language;
- Arabic switches the layout to RTL;
- the device rotates from portrait to landscape;
- RTL and landscape are combined.

Do not change the entire phone language when a per-App locale is available.

## Read the Baseline

```powershell
$serial = "<android-serial>"

adb -s $serial shell cmd locale get-app-locales com.example.qaweek15 --user 0
adb -s $serial shell getprop persist.sys.locale
adb -s $serial shell settings get system accelerometer_rotation
adb -s $serial shell settings get system user_rotation
adb -s $serial shell wm user-rotation
```

Week 16 baseline:

```text
App locales: []
System locale: zh-CN
accelerometer_rotation: 0
user_rotation: 0
wm user-rotation: lock 0
```

## Per-App Locale

Set Chinese:

```powershell
adb -s $serial shell cmd locale set-app-locales com.example.qaweek15 `
  --user 0 --locales zh-CN
adb -s $serial shell am force-stop com.example.qaweek15
adb -s $serial shell am start -W -n com.example.qaweek15/.MainActivity
```

Set Arabic:

```powershell
adb -s $serial shell cmd locale set-app-locales com.example.qaweek15 `
  --user 0 --locales ar
adb -s $serial shell am force-stop com.example.qaweek15
adb -s $serial shell am start -W -n com.example.qaweek15/.MainActivity
```

Clear the App override:

```powershell
adb -s $serial shell cmd locale set-app-locales com.example.qaweek15 --user 0
adb -s $serial shell cmd locale get-app-locales com.example.qaweek15 --user 0
```

Expected final value:

```text
Locales for com.example.qaweek15 for user 0 are []
```

## Android 13+ Locale Source

Reading only `Configuration.getLocales()` during early Activity creation can
return the previous locale while a per-App locale override is still
propagating.

On API 33 and newer, read the application locale directly:

```text
LocaleManager.getApplicationLocales()
```

Fall back to `Configuration.getLocales()` on older versions.

Stable accessibility IDs must not change with language:

```text
fixture-title
fixture-status
request-camera
post-notification
fixture-input
fixture-submit
fixture-reset
fixture-counter
fixture-modal
fixture-webview
```

Only visible text and text direction should change.

## RTL Contract

Arabic must:

- use Arabic visible text;
- set the root layout direction to RTL;
- set text direction from the App locale;
- render the WebView with `dir="rtl"`;
- preserve the same element hierarchy and stable IDs.

## Orientation

On HyperOS Android 14, these commands did not rotate the active fixture:

```text
settings put system user_rotation 1
wm user-rotation lock 1
```

Both left the observed state at `ROTATION_0` / `lock 0`.

Use the UiAutomator2 orientation request while the WebDriver session is alive:

```python
driver.orientation = "LANDSCAPE"
```

The orientation returns to portrait after the session quits. Capture the
screenshot while the session is still open, for example with a short hold:

```python
driver.orientation = "LANDSCAPE"
time.sleep(20)
driver.quit()
```

Do not conclude that orientation failed merely because a screenshot taken
after session teardown is portrait again.

## Week 16 Observation

```text
Chinese per-App locale: PASS
Arabic per-App locale: PASS
RTL layout and WebView direction: PASS
Landscape portrait -> landscape while session alive: PASS
Arabic RTL + landscape: PASS
locale reset to []: PASS
rotation restored to lock 0 / ROTATION_0: PASS
```

The first Arabic run produced mixed Chinese and Arabic text because early
Activity creation read stale Configuration state. Switching to
`LocaleManager.getApplicationLocales()` fixed the source-of-truth issue.

## Restore

```powershell
adb -s $serial shell cmd locale set-app-locales com.example.qaweek15 --user 0
adb -s $serial shell settings put system accelerometer_rotation 0
adb -s $serial shell settings put system user_rotation 0
adb -s $serial shell wm user-rotation lock 0
```

Verify:

```text
App locales: []
accelerometer_rotation: 0
user_rotation: 0
wm user-rotation: lock 0
mRotation: ROTATION_0
```
