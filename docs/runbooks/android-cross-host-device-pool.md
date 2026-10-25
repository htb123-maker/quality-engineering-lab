# Android Cross-Host Appium Device Pool

## Purpose

Verify multiple Appium endpoints running on different hosts, with each endpoint
bound to a device visible to that host.

A device pool is not proven by two local Appium ports alone. The evidence must
show at least two distinct Appium host addresses and successful sessions through
each endpoint.

## Host Prerequisites

For every Appium host:

- Appium is reachable from the pool runner;
- its ADB server sees the configured device as `device`;
- the device serial is valid on that host;
- system and MJPEG ports do not conflict on the same device;
- the firewall permits the Appium HTTP port;
- credentials, if any, come from a secret store.

Appium must listen on an address reachable from the runner, not only
`127.0.0.1`:

```text
appium --address 0.0.0.0 --port 4723
```

Do not expose an Appium server directly to the public internet. Use a private
network, VPN, SSH tunnel, or controlled runner network.

## Pool Configuration

Start from:

```text
configs/android-appium-pool.example.yaml
```

Example:

```yaml
endpoints:
  - name: physical-local
    appium_url: http://127.0.0.1:4723
    serial: REPLACE_WITH_PHYSICAL_SERIAL
    system_port: 8200
    mjpeg_server_port: 7810

  - name: remote-avd
    appium_url: http://192.0.2.10:4723
    serial: emulator-5554
    system_port: 8201
    mjpeg_server_port: 7811
```

The same serial may appear on different hosts. The unique target is the pair:

```text
Appium endpoint + host-local device serial
```

The loader rejects duplicate endpoint targets and invalid service ports.

## Run the Pool Check

```powershell
.\.venv\Scripts\python.exe scripts\verify_android_device_pool.py `
  --pool-config .\pool.local.yaml `
  --json-output artifacts\android-device-pool\pool.json
```

Passing evidence requires:

- every endpoint session passed;
- every capability UDID matches its endpoint serial;
- every session has a distinct session ID;
- every session sees the expected package;
- `host_count >= 2` for cross-host acceptance.

## Week 16 Boundary

The cross-host acceptance has not been executed because only one reachable
Appium host is available in the current environment.

Prepared tooling:

- `configs/android-appium-pool.example.yaml`
- `scripts/verify_android_device_pool.py`
- unit tests for duplicate targets, same serials on different hosts, and port
  validation

Do not report PASS until a real second host endpoint is supplied and
`host_count >= 2`.

## Failure Triage

| Symptom | First check |
| --- | --- |
| Connection refused | Appium bind address, port, firewall, VPN |
| Device not found | ADB inventory on the endpoint host |
| Wrong device | `capability_udid` and host-local serial |
| Duplicate session ID | Pool runner reuse or response mix-up |
| Second host missing | `host_count=1`; block cross-host PASS |
| Duplicate target rejected | Same URL/serial appears twice in YAML |
