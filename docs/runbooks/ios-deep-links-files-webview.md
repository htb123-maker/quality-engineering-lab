# iOS Deep Links, Files, and WebView Triage

## Deep Link

The fixture declares:

```text
qaweek19://
```

The in-App `simulate-deep-link` button routes through the same handler used by
AppDelegate URL dispatch. The expected label is:

```text
deep link: opened qaweek19://system-interactions?case=deep-link
```

This proves the in-App handler. The cloud fixture also supports a true external
cold start after terminating the App:

```python
driver.terminate_app(bundle_id)
driver.execute_script(
    "mobile: deepLink",
    {
        "url": "qaweek19://system-interactions?case=external-cold-start",
        "bundleId": bundle_id,
    },
)
```

`mobile: deepLink` requires Xcode 14.3+ and iOS 16.4+. BrowserStack must use
Appium 2.x explicitly through `bstack:options.appiumVersion`; the provider's
older default does not expose this command. Run `41275681929` proves the path on
iPhone 15 / iOS 17 with Appium 2.19.0.

## File

The fixture writes and reads only:

```text
<Documents>/qa-week19.txt
```

Expected labels:

```text
file: written
file: read week19-file
```

Never search the whole device, print the user home path, or upload App-container
contents as diagnostics.

## WebView

Preferred sequence:

```text
WAIT for WEBVIEW_* context
-> switch context
-> CSS selector #web-status == ready
-> switch back to NATIVE_APP
```

If the provider does not expose a WebView context:

```text
contexts == ['NATIVE_APP']
-> attach contexts and timeout
-> keep the case xfailed, not passed
-> use native page source only as supporting content evidence
```

The fallback proves local HTML content is visible in the native accessibility
snapshot, but it does not prove Web-context switching. Keep that distinction.
On BrowserStack iPhone 15 / iOS 17 + Appium 2.19.0, Run `41275681929` waited
70 seconds and still exposed only `['NATIVE_APP']`; `isInspectable=true` did not
change this provider boundary.

## Background Recovery

The fixture increments a background counter and updates:

```text
background: resumed N
```

After `background_app(1)`, wait for the status prefix instead of sleeping.

## Evidence

Capture final screenshot, page source, WebView mode, current App, device model,
iOS version, and provider session ID. Treat all page source and WebView content
as untrusted input.
