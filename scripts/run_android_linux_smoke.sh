#!/usr/bin/env bash
set -euo pipefail

SERIAL="${1:-emulator-5554}"

adb wait-for-device
for attempt in $(seq 1 120); do
  booted="$(adb -s "$SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')"
  if [ "$booted" = "1" ]; then
    break
  fi
  if [ "$attempt" -eq 120 ]; then
    echo "Android emulator did not finish booting within 240 seconds" >&2
    exit 1
  fi
  sleep 2
done

bash scripts/build_android_fixture.sh "$SERIAL"
mkdir -p artifacts
nohup appium \
  --address 127.0.0.1 \
  --port 4723 \
  --allow-insecure uiautomator2:chromedriver_autodownload \
  > artifacts/appium-android.log 2>&1 &
appium_pid="$!"

cleanup() {
  kill "$appium_pid" 2>/dev/null || true
}
trap cleanup EXIT

for attempt in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:4723/status >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    cat artifacts/appium-android.log
    exit 1
  fi
  sleep 2
done

QA_ANDROID_UDID="$SERIAL" \
QA_ANDROID_DEVICE_NAME=Pixel_API_35_AOSP_ATD \
QA_ANDROID_DEVICE_IDS=local-primary-avd \
uv run --no-sync pytest tests/android -m smoke -q \
  --alluredir=artifacts/allure-android \
  --junitxml=artifacts/android-junit.xml

if [[ "${QA_RUN_ANDROID_BUSINESS_E2E:-0}" == "1" ]]; then
  QA_ANDROID_UDID="$SERIAL" \
  QA_ANDROID_DEVICE_NAME=Pixel_API_35_AOSP_ATD \
  QA_ANDROID_DEVICE_IDS=local-primary-avd \
  uv run --no-sync pytest \
    tests/e2e/test_catalog_cross_layer.py \
    tests/e2e/test_catalog_weak_network.py \
    tests/e2e/test_commerce_cross_layer.py \
    -q \
    --alluredir=artifacts/allure-android-business \
    --junitxml=artifacts/android-business-junit.xml
fi
