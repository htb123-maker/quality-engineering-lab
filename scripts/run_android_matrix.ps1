[CmdletBinding()]
param(
    [string]$PrimarySerial = "",
    [string]$SecondarySerial = "",
    [string]$PhysicalSerial = "",
    [ValidateRange(1, 3)]
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

if (-not $PrimarySerial -and -not $SecondarySerial -and -not $PhysicalSerial) {
    $PrimarySerial = "emulator-5554"
    $SecondarySerial = "emulator-5556"
}

$deviceCandidates = @()
if ($PrimarySerial) {
    $deviceCandidates += [pscustomobject]@{
        ProfileId = "local-primary-avd"
        Serial = $PrimarySerial
        UdidEnv = "QA_ANDROID_UDID_PRIMARY"
        PlatformVersionEnv = $null
    }
}
if ($SecondarySerial) {
    $deviceCandidates += [pscustomobject]@{
        ProfileId = "local-parallel-avd"
        Serial = $SecondarySerial
        UdidEnv = "QA_ANDROID_UDID_SECONDARY"
        PlatformVersionEnv = $null
    }
}
if ($PhysicalSerial) {
    $deviceCandidates += [pscustomobject]@{
        ProfileId = "physical-android"
        Serial = $PhysicalSerial
        UdidEnv = "QA_ANDROID_UDID_PHYSICAL"
        PlatformVersionEnv = "QA_ANDROID_PLATFORM_VERSION_PHYSICAL"
    }
}

if ($deviceCandidates.Count -eq 0) {
    throw "At least one Android device serial must be provided."
}
if ($Workers -gt $deviceCandidates.Count) {
    throw "Requested $Workers workers but only $($deviceCandidates.Count) serials were provided."
}

if (-not (Test-Path -LiteralPath $adb)) {
    throw "adb not found at $adb"
}

$selectedDevices = @($deviceCandidates | Select-Object -First $Workers)
$duplicateSerials = @(
    $selectedDevices |
        Group-Object Serial |
        Where-Object Count -gt 1
)
if ($duplicateSerials.Count -gt 0) {
    throw "Android device serials must be distinct: $($duplicateSerials.Name -join ', ')"
}

foreach ($device in $selectedDevices) {
    $state = (& $adb -s $device.Serial get-state 2>$null | Out-String).Trim()
    if ($state -ne "device") {
        throw "Android device $($device.Serial) is not ready; expected state 'device', got '$state'."
    }
    if ($device.PlatformVersionEnv) {
        $platformVersion = (
            & $adb -s $device.Serial shell getprop ro.build.version.release 2>$null |
                Out-String
        ).Trim()
        if (-not $platformVersion) {
            throw "Could not read Android version from $($device.Serial)."
        }
        [Environment]::SetEnvironmentVariable(
            $device.PlatformVersionEnv,
            $platformVersion,
            "Process"
        )
    }
}

if (-not $SkipFixtureBuild) {
    foreach ($device in $selectedDevices) {
        & (Join-Path $PSScriptRoot "..\apps\android-fixture\build.ps1") `
            -Serial $device.Serial
        if ($LASTEXITCODE -ne 0) {
            throw "Fixture build or install failed for $($device.Serial)."
        }
    }
}

& (Join-Path $PSScriptRoot "start_appium.ps1") `
    -Port $AppiumPort `
    -WaitSeconds 60
if ($LASTEXITCODE -ne 0) {
    throw "Appium did not start on port $AppiumPort."
}

foreach ($envName in @(
    "QA_ANDROID_UDID_PRIMARY",
    "QA_ANDROID_UDID_SECONDARY",
    "QA_ANDROID_UDID_PHYSICAL",
    "QA_ANDROID_DEVICE_IDS"
)) {
    Remove-Item -Path "Env:$envName" -ErrorAction SilentlyContinue
}
foreach ($device in $selectedDevices) {
    [Environment]::SetEnvironmentVariable($device.UdidEnv, $device.Serial, "Process")
}
[Environment]::SetEnvironmentVariable(
    "QA_ANDROID_DEVICE_IDS",
    (($selectedDevices | ForEach-Object ProfileId) -join ","),
    "Process"
)
$selectedSummary = $selectedDevices |
    ForEach-Object { "$($_.ProfileId)=$($_.Serial)" }
Write-Host "Selected Android devices: $($selectedSummary -join ', ')"

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
