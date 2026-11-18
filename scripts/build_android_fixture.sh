#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
SERIAL="${1:-emulator-5554}"

if [[ -z "$SDK_ROOT" ]]; then
  echo "ANDROID_SDK_ROOT or ANDROID_HOME is required" >&2
  exit 1
fi

BUILD_TOOLS="$SDK_ROOT/build-tools/35.0.0"
ANDROID_JAR="$SDK_ROOT/platforms/android-35/android.jar"
OUT="$ROOT/artifacts/android-fixture"
CLASSES="$OUT/classes"
DEX="$OUT/dex"
UNSIGNED="$OUT/fixture-unsigned.apk"
ALIGNED="$OUT/fixture-aligned.apk"
SIGNED="$OUT/fixture-debug.apk"
KEYSTORE="$OUT/debug.keystore"

for tool in javac jar keytool; do
  command -v "$tool" >/dev/null || {
    echo "$tool is required" >&2
    exit 1
  }
done

test -d "$BUILD_TOOLS"
test -f "$ANDROID_JAR"
rm -rf "$CLASSES" "$DEX" "$UNSIGNED" "$ALIGNED" "$SIGNED"
mkdir -p "$CLASSES" "$DEX"

mapfile -t SOURCES < <(find "$ROOT/apps/android-fixture/src" -name '*.java' -print)
javac \
  -source 8 \
  -target 8 \
  -encoding UTF-8 \
  -bootclasspath "$ANDROID_JAR" \
  -d "$CLASSES" \
  "${SOURCES[@]}"

mapfile -t CLASS_FILES < <(find "$CLASSES" -name '*.class' -print)
"$BUILD_TOOLS/d8" --lib "$ANDROID_JAR" --output "$DEX" "${CLASS_FILES[@]}"

"$BUILD_TOOLS/aapt" package \
  -f \
  -M "$ROOT/apps/android-fixture/AndroidManifest.xml" \
  -I "$ANDROID_JAR" \
  -F "$UNSIGNED"

(
  cd "$DEX"
  jar uf "$UNSIGNED" classes.dex
)

if [[ ! -f "$KEYSTORE" ]]; then
  keytool \
    -genkeypair \
    -keystore "$KEYSTORE" \
    -storepass android \
    -keypass android \
    -alias androiddebugkey \
    -dname "CN=Android Debug,O=Android,C=US" \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000
fi

"$BUILD_TOOLS/zipalign" -f -p 4 "$UNSIGNED" "$ALIGNED"
"$BUILD_TOOLS/apksigner" sign \
  --ks "$KEYSTORE" \
  --ks-pass pass:android \
  --key-pass pass:android \
  --out "$SIGNED" \
  "$ALIGNED"

adb -s "$SERIAL" install -r "$SIGNED"
echo "Built and installed $SIGNED on $SERIAL"
