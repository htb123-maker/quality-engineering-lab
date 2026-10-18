# Android Week 15 Fixture

This small Android app provides deterministic device behaviors that the AOSP
test shell cannot request:

- a runtime CAMERA permission prompt;
- a custom deep link at `qaweek15://permission/...`;
- visible foreground and resume state for background recovery checks.

The app has no external dependencies and no production credentials. It is a
test fixture, not the long-term product under test.

Build, sign, and install on the configured emulator:

```powershell
.\apps\android-fixture\build.ps1 -Serial emulator-5554
```

Generated build output, the debug keystore, and the APK stay under the ignored
`artifacts/android-fixture/` directory.
