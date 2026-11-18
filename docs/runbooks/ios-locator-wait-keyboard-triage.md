# iOS Locator, Wait, and Keyboard Triage

## First Classification

Start with the failure boundary, not a locator edit:

```text
Session failure
-> wrong App or screen
-> locator absent
-> element present but hidden
-> input not focused
-> keyboard or system UI
-> gesture consumed by another surface
```

Capture the pytest node ID, current App, window size, screenshot, page source,
Appium log, and the exact `ElementWaitTimeout` or `FlowStepFailure` text.

## Session and App Boundary

Confirm that the session reached the intended App before inspecting elements.

For a local Mac:

```bash
.venv/bin/python scripts/check_ios_environment.py \
  --profile simulator \
  --server-url http://127.0.0.1:4723 \
  --json \
  --output artifacts/week18-ios-environment.json
```

For a cloud provider, verify:

- provider credentials loaded;
- uploaded App ID is correct;
- requested real iPhone and iOS version are available;
- App installation completed before the session returned.

## Locator Strategy

Use this order:

1. Accessibility ID for stable semantic controls.
2. Predicate for attribute combinations that remain readable.
3. Class chain only for a bounded XCUITest hierarchy requirement.

Never translate `resource-id` or `-android uiautomator` into an iOS locator.
`IosLocator` rejects obvious Android markers, but semantic review is still
required.

If accessibility ID is unavailable:

```python
IosLocator.predicate(
    "type == 'XCUIElementTypeButton' AND label == 'Continue'",
    "Continue button",
)
```

Keep predicate expressions small. A long predicate usually means a component
root or application accessibility identifier is missing.

## Wait Strategy

Use the shared `MobileWait` with one explicit expected state:

| State | Use |
| --- | --- |
| `visible` | Read or inspect a displayed element |
| `present` | Detect an element that may be hidden |
| `clickable` | Tap or focus an enabled control |
| `gone` | Confirm a loader, alert, or page completed |

Do not increase the timeout before identifying the missing state. A timeout at
the first frame usually means App launch or environment; a timeout after a
transition usually means navigation or a stale locator.

Focused static checks:

```powershell
$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp-pytest"
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_ios_mobile_framework.py -q -p no:cacheprovider
```

## Keyboard

Keyboard failures are separate from locator failures:

| Evidence | Boundary |
| --- | --- |
| Input element is missing | Locator or screen |
| Element visible but disabled | Control prerequisite |
| Tap succeeds but no keyboard | Focus, hardware keyboard, or system state |
| Text enters but Return has no effect | App behavior or wrong control |
| Keyboard will not hide | XCUITest, App, or system UI |

Use explicit element waits before `IosKeyboard.type_text()`. Attach a screenshot
after the keyboard appears and after it is dismissed.

## Gesture

XCUITest swipe/scroll commands use semantic directions. Check:

1. Current page and foreground App.
2. Whether the gesture target is scrollable.
3. Whether a sheet, alert, or system gesture intercepts input.
4. Whether the next screen root changed after the gesture.

Do not add fixed screen coordinates until the semantic command has been proven
wrong for the specific surface.

## Runtime Smoke

Focused cloud or local iOS smoke:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ios -q `
  -p no:cacheprovider
```

Expected cloud classification:

- local tests skipped on Linux;
- cloud session smoke passed;
- iOS framework smoke passed;
- Allure contains screenshot and window size;
- any project-App test remains `NOT RUN` until `IOS_CLOUD_APP` is configured.
