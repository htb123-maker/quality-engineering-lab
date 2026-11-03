# Cross-Platform Scenario Failure Triage / 跨平台场景失败排查

## 1. Identify The Layer / 先定位失败层

Start with the `ScenarioStepFailure`:

```text
scenario_id
+ step_id
+ step name
+ original cause
```

Then classify the failure:

| Signal | Likely layer |
| --- | --- |
| Missing semantic key | Test code / adapter contract |
| Element or text timeout | Product, locator, or wait |
| Session creation failure | Device, Appium, WDA, or environment |
| File write/read mismatch | Product behavior or test data |
| Adapter factory missing | Framework wiring |

## 2. Check Platform Isolation / 检查平台隔离

- Confirm the selected adapter matches the device platform.
- Confirm business scenarios contain no platform conditionals.
- Confirm the semantic locator exists for that platform.
- Confirm the test uses the intended fixture and device serial.

## 3. Collect Evidence / 收集证据

The adapter writes:

```text
artifacts/cross-platform/week22/<run-id>/<platform>/
+- CP-...-step.png
+- CP-...-step.xml
+- CP-...-step.failure.json
```

The manifest must not contain access keys, passwords, tokens, or full UDIDs.

## 4. Platform-Specific Checks / 平台专项检查

Android:

- `adb devices -l`
- fixture package installed
- Appium `/status`
- temporary file path exists and is writable
- deep-link intent reaches the fixture Activity

iOS:

- Xcode and Simulator available
- fixture app installed
- XCUITest/WDA session established
- accessibility identifiers present in page source
- `delete-file` control available

## 5. Completion Rule / 完成规则

Do not convert a platform failure to `skip` merely to make the shared suite
green. Fix the adapter or keep the platform result explicit as `FAILED`,
`BLOCKED`, or `DEFERRED`.
