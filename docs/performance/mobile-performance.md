# Mobile Performance Evidence

Mobile performance uses platform telemetry and device-side commands. Appium is
the interaction layer; it is not the measurement source.

## 1. Measurement Model

```text
Source-controlled fixture
-> ADB lifecycle commands
-> real UI interaction
-> Android platform counters
-> structured JSON evidence
-> explicit PASS / PARTIAL / FAILED / DEFERRED
```

Week 30 implements an Android real-device path and an iOS device-cloud path:

| Signal | Source | What it answers |
| --- | --- | --- |
| Cold launch | `am start -W -S` | How long ActivityManager reports for a stopped-process launch |
| Warm launch | HOME, then `am start -W` | How long ActivityManager reports for a background-to-front launch |
| Jank | `dumpsys gfxinfo <package>` | How many rendered frames missed their deadline |
| Memory | `dumpsys meminfo <package>` | Current PSS and RSS footprint |
| CPU | `/proc/<pid>/stat` over a measured window | Process CPU use during real taps |
| Battery | `dumpsys battery` | Power context, not a controlled energy experiment |
| iOS cold/warm control path | Appium `terminateApp` / `activateApp` | Runner-to-cloud command and UI-ready time |
| iOS weak network | BrowserStack `networkProfile` | Whether a real app request slows, fails, and recovers |

## 2. Interaction Rule

Never accept `0% jank` when `Total frames rendered` is zero. No rendered sample
means no jank conclusion. The collector locates `fixture-counter` in the live UI
tree and taps its center 40 times after resetting graphics statistics.

## 3. Result Recording

The canonical evidence contains:

- device manufacturer, model, Android release/API, build fingerprint, display;
- app package, Activity, version, and installed path;
- every launch sample and its p50/p95/min/max;
- background focus before and after resume;
- frame and jank counters, plus missed-vsync and slow-frame reasons;
- PSS/RSS and category memory values;
- process CPU, online CPU count, and measurement duration;
- battery start/end context and whether energy delta is interpretable;
- machine checks, limitations, weak-network status, and iOS status.

The Week 30 run is recorded in
[`reports/weekly/WEEK-30.md`](../../reports/weekly/WEEK-30.md).

## 4. Current Acceptance Boundary

The Android mobile collector does not yet run the catalog network journey.
Weak-network acceptance for Android needs the existing fixture request through
`adb reverse` plus a Toxiproxy latency, bandwidth, or timeout fault.

Battery energy likewise needs a controlled unplugged run with a stable starting
level, fixed brightness, radio state, and a meaningful observation window. A USB
powered snapshot is retained as context but is not promoted to an energy result.

iOS device-cloud evidence now measures the Appium control path:

| Metric | iPhone 15 / iOS 17.3 |
| --- | ---: |
| Session ready | 18,860.57 ms |
| Cold p95 | 2,356.514 ms |
| Warm resume p95 | 990.331 ms |

This is not first-frame rendering. Instruments, `xctrace`, and MetricKit remain
`DEFERRED` until a macOS runner can collect native traces.

The controlled iOS weak-network journey produced:

| Phase | Result |
| --- | --- |
| Baseline | `active`, 633.555 ms |
| `3g-umts-lossy` | `active`, 1563.99 ms, 2.469x slower |
| `no-network` | observable `NSURLError` |
| `reset` | `active`, 589.499 ms |

## 5. Reproducible Run

```powershell
.\scripts\collect_android_mobile_performance.ps1 `
  -Serial <serial> `
  -Output artifacts\performance\week30\android\mobile-performance.json
```

Read the generated JSON `status` and `checks`; do not infer a result from the
process exit code alone.

iOS cloud evidence is written under
`artifacts/performance/week30/ios-cloud/`. The command and provider workflow
details are in `docs/runbooks/ios-cloud-performance-and-weak-network.md`.
