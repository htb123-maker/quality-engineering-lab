# iOS Test Fixture

Week 19 fixture for deterministic iOS system interactions:

- camera and microphone permission prompts;
- local notification authorization and scheduling;
- an in-app deep-link handler using `qaweek19://`;
- app-container file write/read state;
- a local WKWebView with a deterministic page;
- foreground/background recovery counters.

The app has no third-party dependencies and no production credentials.

Build an unsigned real-device `.ipa` on macOS:

```bash
xcodebuild \
  -project apps/ios-fixture/QaIosFixture.xcodeproj \
  -scheme QaIosFixture \
  -configuration Debug \
  -sdk iphoneos \
  -derivedDataPath artifacts/ios-fixture-derived \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  build
```

The GitHub workflow packages the resulting `.app` into an `.ipa`, uploads it to
BrowserStack, and runs the Week 19 cloud suite.
