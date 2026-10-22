# Android Test Fixture

This small Android app provides deterministic device behaviors that the AOSP
test shell cannot request:

- a runtime CAMERA permission prompt;
- a runtime notification-permission prompt and a fixed `qa-week15-status` channel;
- a deterministic notification with a PendingIntent back to the fixture;
- light/dark theme switching with a color-scheme-aware WebView;
- English, Chinese, and Arabic fixture text with RTL layout support;
- a form with validation, reset, counter, and dialog state;
- a custom deep link at `qaweek15://permission/...`;
- visible foreground and resume state for background recovery checks.

The app has no external dependencies and no production credentials. It is a
test fixture, not the long-term product under test.

Build, sign, and install on the configured emulator:

```powershell
.\apps\android-fixture\build.ps1 -Serial emulator-5554
```

For the two-AVD Week 16 matrix:

```powershell
.\scripts\run_android_matrix.ps1 `
  -PrimarySerial emulator-5554 `
  -SecondarySerial emulator-5556 `
  -Workers 2
```

Generated build output, the debug keystore, and the APK stay under the ignored
`artifacts/android-fixture/` directory.
