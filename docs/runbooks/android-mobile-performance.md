# Android Mobile Performance Collection

Week 30 uses device-level evidence instead of Appium command duration. Appium
drives UI actions, but it is not a mobile performance engine.

## 1. Preconditions

- `adb` is available through `ANDROID_HOME` or `PATH`.
- One physical Android device or AVD is in state `device`.
- The target package is installed.
- The screen can be woken and the device is not on a secure lock screen.
- The host is connected to power because the run creates repeated launches.

Check the target:

```powershell
adb devices -l
adb -s <serial> shell getprop ro.product.model
adb -s <serial> shell pm path com.example.qaweek15
```

## 2. Build The Fixture

Build and install the source-controlled fixture:

```powershell
$env:PATH = "D:\Android\Sdk\platform-tools;$env:PATH"
.\apps\android-fixture\build.ps1 -Serial <serial>
```

If Android reports `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, the installed test
fixture has a different signing key. Remove only the test package, then install
again:

```powershell
adb -s <serial> uninstall com.example.qaweek15
adb -s <serial> install -r .\artifacts\android-fixture\fixture-debug.apk
```

Do not use this reset procedure for a production application.

## 3. Run The Collector

```powershell
.\scripts\collect_android_mobile_performance.ps1 `
  -Serial <serial> `
  -ColdRuns 10 `
  -WarmRuns 10 `
  -Taps 40 `
  -Output artifacts\performance\week30\android\mobile-performance.json
```

The collector performs:

1. Ten force-stop and `am start -W -S` cold-launch samples.
2. Ten HOME-to-relaunch warm-launch samples.
3. One verified background recovery cycle.
4. A `gfxinfo` reset followed by 40 real counter taps.
5. Frame, jank, memory, and process CPU collection.
6. Device, app, display, and battery metadata capture.

The fixture is force-stopped after a successful collection.

## 4. Interpret The Result

The JSON status is `PASS` only when every machine check passes. The checks are:

| Check | Default threshold |
| --- | ---: |
| Cold launch p95 | `<= 5000 ms` |
| Warm launch p95 | `<= 2000 ms` |
| Background resume | `<= 1500 ms` |
| Rendered frames | `>= 30` |
| Janky frames | `<= 5%` |
| Total PSS present | `>= 1024 KB` |

These thresholds are project guardrails, not universal Android industry limits.
Keep the device, build fingerprint, fixture version, and thresholds in the
evidence whenever results are compared.

## 5. Failure Triage

| Symptom | Check | Meaning |
| --- | --- | --- |
| No `TotalTime` | `dumpsys window`, screen power | The launch command did not return valid ActivityManager timing |
| Zero frames | `uiautomator dump`, target bounds | No real UI interaction was generated |
| Missing `fixture-counter` | Installed APK path/version | The device does not have the current fixture |
| PSS command fails | `pidof <package>` | The app exited before resource collection |
| Device is charging | `dumpsys battery` | Battery percentage cannot support an energy conclusion |
| Focus stays on app after HOME | Launcher/window state | Background recovery was not established |

Retry an invalid launch observation only after checking screen power and target
focus. Do not replace a missing duration with zero.

## 6. Limits

- `am start -W` is ActivityManager timing, not first-frame rendering.
- `gfxinfo` covers the selected package's rendering history since reset.
- PSS and RSS describe one snapshot, not leak growth over time.
- USB charging makes short battery percentage changes non-interpretable.
- A device without a network-dependent journey cannot validate weak-network
  behavior by merely disabling connectivity.
- AVD results do not establish physical GPU, thermal, radio, or OEM policy
  behavior.
