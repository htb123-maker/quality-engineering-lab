# Android Dark Mode, Font Scale, and Display Density

## Purpose

Verify that Native Android controls and the fixture WebView remain readable
when system UI configuration changes:

- light and dark mode;
- normal and large font scale;
- lower and higher display density;
- one combined stress configuration.

Always record and restore the original device configuration.

## Read the Baseline

```powershell
$serial = "<android-serial>"

adb -s $serial shell cmd uimode night
adb -s $serial shell settings get system font_scale
adb -s $serial shell wm density
adb -s $serial shell wm size
```

Week 16 baseline on Redmi K50:

```text
Night mode: no
font_scale: 1.0
Physical density: 560
Physical size: 1440x3200
```

## Fixture Theme Contract

The fixture selects its theme before `super.onCreate`:

```text
UI_MODE_NIGHT_YES -> Theme.Material.NoActionBar
otherwise         -> Theme.Material.Light.NoActionBar
```

The WebView CSS follows the same system preference:

```css
@media (prefers-color-scheme: dark) {
  body { background: #121212; color: #f5f5f5; }
}
```

A fixed `Theme.Material.Light` is not sufficient because it prevents the
system dark configuration from reaching Native controls.

## Dark Mode

```powershell
adb -s $serial shell cmd uimode night yes
adb -s $serial shell am force-stop com.example.qaweek15
adb -s $serial shell am start -W -n com.example.qaweek15/.MainActivity
adb -s $serial exec-out screencap -p > dark-mode.png
```

Expected:

- dark Native background and controls;
- readable light text;
- dark WebView background with light heading;
- no clipping or overlap.

Restore:

```powershell
adb -s $serial shell cmd uimode night no
```

## Font Scale

Test:

```powershell
adb -s $serial shell settings put system font_scale 1.3
adb -s $serial shell am force-stop com.example.qaweek15
adb -s $serial shell am start -W -n com.example.qaweek15/.MainActivity

adb -s $serial shell settings put system font_scale 1.5
adb -s $serial shell am force-stop com.example.qaweek15
adb -s $serial shell am start -W -n com.example.qaweek15/.MainActivity
```

Do not depend on sending `android.intent.action.CONFIGURATION_CHANGED` from a
shell UID. On HyperOS Android 14 this is denied with `SecurityException`.
Restarting the Activity is sufficient to observe the new scale.

Expected:

- title, status, form labels, and buttons remain inside screen bounds;
- no text overlaps the next control;
- WebView heading remains readable.

Restore:

```powershell
adb -s $serial shell settings put system font_scale 1.0
```

## Display Density

Use overrides without changing the physical resolution:

```powershell
adb -s $serial shell wm density 420
adb -s $serial shell am force-stop com.example.qaweek15
adb -s $serial shell am start -W -n com.example.qaweek15/.MainActivity

adb -s $serial shell wm density 640
adb -s $serial shell am force-stop com.example.qaweek15
adb -s $serial shell am start -W -n com.example.qaweek15/.MainActivity
```

Expected:

- controls remain horizontally bounded;
- vertical scrolling remains available;
- no button text is clipped;
- changes do not modify `wm size`.

Restore:

```powershell
adb -s $serial shell wm density reset
```

## Combined Stress

Test:

```powershell
adb -s $serial shell cmd uimode night yes
adb -s $serial shell settings put system font_scale 1.5
adb -s $serial shell wm density 640
adb -s $serial shell am force-stop com.example.qaweek15
adb -s $serial shell am start -W -n com.example.qaweek15/.MainActivity
```

## Week 16 Observation

```text
Dark mode: PASS
font_scale=1.3: PASS
font_scale=1.5: PASS
density=420: PASS
density=640: PASS
dark + 1.5 + 640: PASS
restored: Night mode no, font_scale 1.0, density 560, size 1440x3200
```

The first dark-mode attempt remained light because the fixture used a fixed
light theme. The issue was fixed by selecting the platform theme before
Activity creation. The screenshot comparison is part of the acceptance; a
system setting alone does not prove the App responded.

## Restore Checklist

```powershell
adb -s $serial shell cmd uimode night no
adb -s $serial shell settings put system font_scale 1.0
adb -s $serial shell wm density reset

adb -s $serial shell cmd uimode night
adb -s $serial shell settings get system font_scale
adb -s $serial shell wm density
adb -s $serial shell wm size
```

Expected baseline:

```text
Night mode: no
1.0
Physical density: 560
Physical size: 1440x3200
```
