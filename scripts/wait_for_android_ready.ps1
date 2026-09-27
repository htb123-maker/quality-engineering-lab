[CmdletBinding()]
param(
    [string]$Serial = "emulator-5554",
    [ValidateRange(10, 600)]
    [int]$TimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$adb = if ($env:ANDROID_HOME) {
    Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
} else {
    "D:\Android\Sdk\platform-tools\adb.exe"
}

if (-not (Test-Path -LiteralPath $adb)) {
    throw "adb not found at $adb"
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$lastStatus = [ordered]@{
    serial = $Serial
    state = "unknown"
    boot_completed = "unknown"
    bootanim = "unknown"
    package_service = "unknown"
    settings_service = "unknown"
}

while ((Get-Date) -lt $deadline) {
    $state = (& $adb -s $Serial get-state 2>$null | Out-String).Trim()
    if ($state -eq "device") {
        $bootCompleted = (
            & $adb -s $Serial shell getprop sys.boot_completed 2>$null |
                Out-String
        ).Trim()
        $bootAnim = (
            & $adb -s $Serial shell getprop init.svc.bootanim 2>$null |
                Out-String
        ).Trim()
        $packageService = (
            & $adb -s $Serial shell service check package 2>$null |
                Out-String
        ).Trim()
        $settingsService = (
            & $adb -s $Serial shell service check settings 2>$null |
                Out-String
        ).Trim()

        $lastStatus.state = $state
        $lastStatus.boot_completed = $bootCompleted
        $lastStatus.bootanim = $bootAnim
        $lastStatus.package_service = $packageService
        $lastStatus.settings_service = $settingsService

        if (
            $bootCompleted -eq "1" -and
            $bootAnim -eq "stopped" -and
            $packageService -match "found" -and
            $settingsService -match "found"
        ) {
            [pscustomobject]$lastStatus | ConvertTo-Json -Compress
            exit 0
        }
    }

    Start-Sleep -Seconds 2
}

throw "Android device did not become ready within $TimeoutSeconds seconds: $([pscustomobject]$lastStatus | ConvertTo-Json -Compress)"
