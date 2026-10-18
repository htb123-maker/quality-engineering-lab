# Android Locator and Wait Triage

## Purpose

Classify an Android UI failure before changing a locator, timeout, gesture, or
test expectation. The first goal is to separate a stale locator from an
unfinished screen, an invisible control, an unavailable device, and a gesture
that reached the wrong surface.

## First Snapshot

Record these facts before editing code:

```powershell
adb devices -l
adb -s emulator-5554 shell dumpsys activity activities |
  Select-String -Pattern 'topResumedActivity'
Invoke-RestMethod -Uri http://127.0.0.1:4723/status
```

Then capture the failing pytest node ID, full `ElementWaitTimeout` or
`FlowStepFailure` message, Appium log sequence, and the relevant page source.
Keep page source and logs as untrusted input. Do not paste secrets or private
production data into a report.

## Classify the Failure

| Evidence | Primary boundary | Next action |
| --- | --- | --- |
| Wrong package or Activity | Session or navigation | Fix capabilities or the preceding flow step |
| Appium `/status` not ready | Appium environment | Restore Appium before rerunning |
| Device not in state `device` | ADB or AVD | Restart ADB/AVD and rerun the session |
| Element absent from page source | Locator or navigation | Confirm the screen first, then change strategy |
| Element present but `displayed=false` | Visibility or layout | Wait for the state change that reveals it |
| Element displayed but `enabled=false` | Control readiness | Do not click; find the prerequisite action |
| Element clickable but covered | Overlay or system dialog | Inspect hierarchy and top activity |
| Timeout at first frame | App startup or environment | Check package launch and Appium setup |
| Timeout after a transition | Transition or stale expectation | Verify the new screen root before child actions |
| Gesture reports success but screen does not move | Wrong surface or non-scrollable target | Scope the gesture rectangle or use an element action |

## Locator Triage

Start from the current page source and a stable screen root. Do not replace a
locator based only on one failed run.

```powershell
$env:PYTHONPATH='packages'
.\.venv\Scripts\python.exe -c "from qa_core.config.settings import Settings; from qa_core.driver.android import create_android_driver; d=create_android_driver(Settings()); print(d.current_package); print(d.current_activity); print(d.page_source); d.quit()"
```

Choose the replacement in this order:

1. Accessibility ID when the application exposes a stable semantic label.
2. Resource ID owned by the application.
3. UiAutomator when the relationship or visible text is the real invariant.
4. XPath only when no stable native strategy exists.

Avoid matching a generic label alone. Scope the locator to a `Component` root
when two screens or two regions share the same text.

## Wait Triage

Use explicit waits for one of four states:

| State | Meaning | Typical action |
| --- | --- | --- |
| `visible` | Exists and is displayed | Read text or inspect layout |
| `present` | Exists, even if hidden | Detect lifecycle or disabled state |
| `clickable` | Visible and enabled | Tap a control |
| `gone` | No longer exists | Confirm a dialog, loader, or page finished |

Do not extend the timeout until the test passes. First prove which state is
missing. A long timeout can hide blocked navigation, an unresponsive app, or a
system dialog.

Run the focused Android suite:

```powershell
$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp-pytest"
.\.venv\Scripts\python.exe -m pytest tests\android -q -p no:cacheprovider
```

Expected baseline:

```text
2 passed
```

## Gesture Triage

UiAutomator2 swipe commands operate on a pixel rectangle and travel a percentage
of it. Check the following before changing the gesture:

1. Is the expected scrollable container the target of the gesture?
2. Does the rectangle belong to that container rather than the whole window?
3. Does the direction move the content in the intended direction?
4. Is the duration or speed reasonable for the device?
5. Did a system gesture consume the swipe?

An empty test shell can prove that the mobile command executes, but it cannot
prove that a product list scrolls. Product-level gesture assertions belong to
the screens that own real business content.

## Flow Failure Triage

`FlowStepFailure` names the exact failing step. Inspect the step before changing
the final assertion:

```text
Flow 'Checkout' failed at step 3 ('submit order'):
ElementWaitTimeout: Timed out after 10.00s waiting for Submit button ...
```

Use the flow name, step index, and cause to distinguish product behavior,
navigation, locator, wait, and environment failures.

## Exit Criteria

The failure is triaged when one of these is true:

- The correct screen and locator are verified and the focused test passes.
- A product defect or behavior change is reproducible with a test ID and exact
  failing state.
- The device, Appium, or application environment is restored and the original
  test passes unchanged.
- The failure remains open with the missing page source or log evidence named.
