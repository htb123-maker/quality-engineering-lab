[CmdletBinding()]
param(
    [string]$PrimarySerial = "emulator-5554",
    [string]$SecondarySerial = "emulator-5556",
    [ValidateRange(1, 2)]
    [int]$Workers = 2,
    [ValidateRange(1, 65535)]
    [int]$AppiumPort = 4723,
    [switch]$SkipFixtureBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$adb = if ($env:ANDROID_HOME) {
    Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
} else {
    "D:\Android\Sdk\platform-tools\adb.exe"
}
$serials = @($PrimarySerial, $SecondarySerial)

if ($Workers -gt $serials.Count) {
    throw "Requested $Workers workers but only $($serials.Count) serials were provided."
}

if (-not (Test-Path -LiteralPath $adb)) {
    throw "adb not found at $adb"
}

foreach ($serial in $serials[0..($Workers - 1)]) {
    $state = (& $adb -s $serial get-state 2>$null | Out-String).Trim()
    if ($state -ne "device") {
        throw "Android device $serial is not ready; expected state 'device', got '$state'."
    }
}

if (-not $SkipFixtureBuild) {
    foreach ($serial in $serials[0..($Workers - 1)]) {
        & (Join-Path $PSScriptRoot "..\apps\android-fixture\build.ps1") `
            -Serial $serial
        if ($LASTEXITCODE -ne 0) {
            throw "Fixture build or install failed for $serial."
        }
    }
}

& (Join-Path $PSScriptRoot "start_appium.ps1") `
    -Port $AppiumPort `
    -WaitSeconds 60
if ($LASTEXITCODE -ne 0) {
    throw "Appium did not start on port $AppiumPort."
}

$env:QA_ANDROID_UDID_PRIMARY = $PrimarySerial
$env:QA_ANDROID_UDID_SECONDARY = $SecondarySerial
$env:PYTEST_DEBUG_TEMPROOT = Join-Path $root ".tmp-pytest"

$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$runRoot = Join-Path $root "artifacts\android-matrix\$runId"
$allureResults = Join-Path $runRoot "allure-results"
$consoleLog = Join-Path $runRoot "pytest-console.log"
New-Item -ItemType Directory -Path $allureResults -Force | Out-Null

$python = Join-Path $root ".venv\Scripts\python.exe"
$pytestArguments = @(
    "-m", "pytest",
    "tests\android",
    "-q",
    "-n", "$Workers",
    "--dist", "load",
    "-p", "no:cacheprovider",
    "--alluredir=$allureResults"
)

Push-Location -LiteralPath $root
try {
    & $python @pytestArguments 2>&1 | Tee-Object -FilePath $consoleLog
    $pytestExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

$allureCommand = Get-Command allure -ErrorAction SilentlyContinue
if ($allureCommand) {
    & $allureCommand.Source generate $allureResults --clean `
        -o (Join-Path $runRoot "allure-report")
}
else {
    Write-Host "Allure CLI is not installed; raw results remain in $allureResults."
}

Write-Host "Android matrix evidence: $runRoot"
exit $pytestExitCode
