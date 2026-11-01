# iOS Parallel WDA and DerivedData Triage

## Classify First

```text
matrix did not resolve two devices
-> worker count exceeds active profiles
-> Simulator not Booted
-> Appium server not ready
-> port collision
-> WDA build or launch failure
-> XCUITest session invalidated
-> test logic failure
```

Do not rerun repeatedly before checking the worker profile and resource record.

## Confirm Worker Binding

```bash
cat artifacts/ios-week20/<run-id>/<device-id>.json
.venv/bin/python scripts/verify_ios_parallel_resources.py \
  --run-dir artifacts/ios-week20/<run-id> \
  --expected-workers 2
```

Each worker must have a distinct:

- logical device ID;
- UDID;
- Appium server port;
- WDA local port;
- DerivedData path.

## Check Simulator State

```bash
xcrun simctl list devices
```

The selected UDIDs must both be `Booted`. The workflow waits for at most 120
polls rather than allowing `simctl bootstatus` to block indefinitely.

## Check Ports

```bash
lsof -nP -iTCP:4723 -sTCP:LISTEN
lsof -nP -iTCP:4724 -sTCP:LISTEN
lsof -nP -iTCP:8100 -sTCP:LISTEN
lsof -nP -iTCP:8101 -sTCP:LISTEN
```

Appium and WDA ports serve different layers. A free Appium port does not imply a
free WDA port. Inspect the matching `appium-ios-matrix-<port>.log`.

## Check DerivedData

```bash
find artifacts/ios-derived/<run-id> -maxdepth 2 -type d
```

Each device must have its own directory. Do not delete or clean shared
DerivedData as a first response; preserve the paths and build logs as evidence.

## Invalid Session

If `create_ios_driver` returns but the first command reports
`InvalidSessionIdException`:

1. identify the worker's Appium server port from its JSON record;
2. inspect the corresponding Appium log;
3. confirm both Simulators remained `Booted`;
4. verify `useNewWDA`, `derivedDataPath`, and WDA ports;
5. check whether the other worker passed while sharing an Appium server.

Each matrix worker is intended to use its own Appium process and port. A shared
server is not sufficient evidence for resource isolation.

## Exit Criteria

The failure is triaged when one is true:

- both workers complete with unique, overlapping resources;
- a provider or host limitation is reproduced with exact ports and logs;
- a Driver/session defect is reproduced on one worker while the other passes;
- the environment is corrected and the unchanged matrix test passes.
