# ADR-0015: Business-Realistic Evidence and Android Device Matrix

## Context

A test fixture is useful for deterministic UI, permission, file, and recovery
checks, but it cannot by itself prove that a business workflow is credible.
Likewise, two emulators using the same API level do not constitute an OEM or
version matrix.

Week 32 post-acceptance review found two test-platform defects:

- parallel Android workers shared `systemPort` and `mjpegServerPort`;
- a Chinese physical device changed localized text while tests asserted English.

It also found a real physical-device Hybrid limitation: the installed WebView
was Android System WebView 130 while the Appium bundle used ChromeDriver 124.
Switching context crashed an xdist worker.

## Decision

1. Fixture-only success remains valid only for fixture contracts. A business
   claim requires a real SUT path through authentication, role/state setup, the
   mobile action, and final API or database verification.
2. Android CI runs the real catalog cross-layer suite and the Toxiproxy weak
   network recovery test in addition to fixture smoke tests.
3. The weak-network test must use a real SUT item/session and verify recovery
   after an actual delayed or dropped API path. It cannot substitute a local
   "network error" button.
4. Each Android xdist worker receives distinct UDID, `systemPort`, and
   `mjpegServerPort` values.
5. Fixture tests use a deterministic per-app locale instead of changing the
   whole device language.
6. Hybrid tests on physical devices require a ChromeDriver matching the active
   WebView major. A mismatch is a platform gap and remains `FAILED` or `NOT RUN`.
7. AOSP API 15 emulators plus Redmi Android 14 provide useful interoperability
   evidence but are not a complete OEM/API matrix.

## Consequences

- Catalog business regression is now continuously executed on Android CI.
- The weak-network claim has real API and UI recovery evidence.
- Parallel device failures are attributable to the correct worker/device port.
- Physical WebView Hybrid remains open until a matching driver is provisioned.
- Cross-host device pools, non-charging battery measurement, and a full
  order/payment/inventory product flow remain outside the completed core scope.
