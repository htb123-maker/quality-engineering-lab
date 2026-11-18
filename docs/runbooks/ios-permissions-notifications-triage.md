# iOS Permissions and Notifications Triage

## Classify First

```text
App not foreground
-> control missing
-> prompt missing
-> wrong prompt action
-> status did not update
-> notification not scheduled
```

Do not rerun repeatedly without checking the current App, iOS version, alert
text, status label, screenshot, and page source.

## Permission Prompt

The fixture buttons are:

```text
request-camera
request-microphone
request-notifications
```

After tapping one button, `IosSystemAlerts` waits up to its deadline for the
Appium alert endpoint. Expected statuses are exact fixture strings:

```text
camera: granted
microphone: denied
notifications: authorized
notifications: scheduled
```

If no alert appears:

1. confirm the fixture is the foreground App;
2. check whether the permission state was already decided;
3. inspect whether the provider automatically handled the system alert;
4. attach screenshot and page source;
5. classify as App, system UI, or provider boundary.

The cloud App is freshly installed per workflow run. Reusing one session for
multiple permission scenarios can leave non-resettable state.

Camera and microphone can be reset through the XCUITest Driver on real devices:

```python
driver.execute_script("mobile: resetPermission", {"service": "camera"})
```

Run `41275681929` used this path for grant, deny, reset and relaunch recovery on
iPhone 15 / iOS 17. Notification authorization has no equivalent service in the
current Driver command list, so a notification test must not assume it can reset
system state.

## Notification

`send-notification` schedules a one-second local notification after
authorization. The test checks the in-App status, not production push delivery.

Notification Center display and notification-tap deep-link behavior remain
additional system-UI checks. A missing notification banner is not automatically
a product defect when the provider suppresses system overlays.

The fixture registers `UNUserNotificationCenterDelegate` and records a response
in `fixture.notificationOpened`, but Run `41275681929` did not automate opening
Notification Center or tapping the banner. Keep those cases `NOT RUN` until a
SpringBoard-compatible path is proven on the selected provider.

## Evidence

Keep:

- test ID and pytest node ID;
- real device and iOS version;
- system prompt screenshot;
- post-action status label;
- page source;
- per-step screenshot/page-source files from `ios-week19-screenshots`;
- XCUITest/Appium provider log;
- Allure result directory.

## Exit Criteria

The failure is triaged when one is true:

- the correct prompt action and status are proven and the test passes;
- system or provider limitation is reproducible with evidence;
- an App defect is reproducible with the exact button, prompt, and status;
- the environment is restored and the original test passes unchanged.
