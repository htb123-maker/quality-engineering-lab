[CmdletBinding()]
param(
    [string]$Serial = "emulator-5554",
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$sdkRoot = if ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } else { "D:\Android\Sdk" }
$buildTools = Join-Path $sdkRoot "build-tools\35.0.0"
$androidJar = Join-Path $sdkRoot "platforms\android-35\android.jar"
$outputRoot = Join-Path $root "artifacts\android-fixture"
$classesDir = Join-Path $outputRoot "classes"
$dexDir = Join-Path $outputRoot "dex"
$unsignedApk = Join-Path $outputRoot "fixture-unsigned.apk"
$alignedApk = Join-Path $outputRoot "fixture-aligned.apk"
$signedApk = Join-Path $outputRoot "fixture-debug.apk"
$keystore = Join-Path $outputRoot "debug.keystore"

function Resolve-JavaHome {
    $candidates = @(
        (Join-Path $env:USERPROFILE ".jdks\corretto-1.8.0_472"),
        $env:JAVA_HOME,
        "D:\python charm\PyCharm 2025.3\jbr",
        (Join-Path $env:USERPROFILE ".jdks\openjdk-25.0.1")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate "bin\javac.exe"))) {
            return $candidate
        }
    }
    throw "No JDK with javac found. Set JAVA_HOME."
}

$javaHome = Resolve-JavaHome
$javac = Join-Path $javaHome "bin\javac.exe"
$jar = Join-Path $javaHome "bin\jar.exe"
$keytool = Join-Path $javaHome "bin\keytool.exe"

foreach ($path in @($buildTools, $androidJar)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Android build dependency not found: $path"
    }
}

$generatedPaths = @($classesDir, $dexDir, $unsignedApk, $alignedApk, $signedApk)
foreach ($path in $generatedPaths) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $outputRoot, $classesDir, $dexDir -Force | Out-Null

$sources = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "src") -Recurse -Filter "*.java"
& $javac `
    -source 8 `
    -target 8 `
    -encoding UTF-8 `
    -bootclasspath $androidJar `
    -d $classesDir `
    $sources.FullName
if ($LASTEXITCODE -ne 0) {
    throw "javac failed with exit code $LASTEXITCODE."
}

$classFiles = Get-ChildItem -LiteralPath $classesDir -Recurse -Filter "*.class"
& (Join-Path $buildTools "d8.bat") `
    --lib $androidJar `
    --output $dexDir `
    $classFiles.FullName
if ($LASTEXITCODE -ne 0) {
    throw "d8 failed with exit code $LASTEXITCODE."
}

& (Join-Path $buildTools "aapt.exe") package `
    -f `
    -M (Join-Path $PSScriptRoot "AndroidManifest.xml") `
    -I $androidJar `
    -F $unsignedApk
if ($LASTEXITCODE -ne 0) {
    throw "aapt package failed with exit code $LASTEXITCODE."
}

Push-Location -LiteralPath $dexDir
try {
    & $jar uf $unsignedApk "classes.dex"
    if ($LASTEXITCODE -ne 0) {
        throw "Adding classes.dex failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $keystore)) {
    & $keytool `
        -genkeypair `
        -keystore $keystore `
        -storepass android `
        -keypass android `
        -alias androiddebugkey `
        -dname "CN=Android Debug,O=Android,C=US" `
        -keyalg RSA `
        -keysize 2048 `
        -validity 10000
    if ($LASTEXITCODE -ne 0) {
        throw "Creating the debug keystore failed with exit code $LASTEXITCODE."
    }
}

& (Join-Path $buildTools "zipalign.exe") -f -p 4 $unsignedApk $alignedApk
if ($LASTEXITCODE -ne 0) {
    throw "zipalign failed with exit code $LASTEXITCODE."
}

& (Join-Path $buildTools "apksigner.bat") sign `
    --ks $keystore `
    --ks-pass pass:android `
    --key-pass pass:android `
    --out $signedApk `
    $alignedApk
if ($LASTEXITCODE -ne 0) {
    throw "apksigner failed with exit code $LASTEXITCODE."
}

Write-Host "Built $signedApk"

if (-not $SkipInstall) {
    $adb = Get-Command adb -ErrorAction Stop
    & $adb.Source -s $Serial install -r $signedApk
    if ($LASTEXITCODE -ne 0) {
        throw "APK installation failed with exit code $LASTEXITCODE."
    }
}
