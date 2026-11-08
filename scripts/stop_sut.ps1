[CmdletBinding()]
param(
    [switch]$RemoveVolumes,

    [switch]$FaultInjection,

    [string]$ProjectName = "",

    [string]$EnvFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $root "apps\compose\compose.yaml"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop with the Compose plugin first."
}

Push-Location $root

try {
    $compose = @("compose")
    if ($ProjectName) {
        $compose += @("-p", $ProjectName)
    }
    $resolvedEnvFile = if ($EnvFile) {
        if ([System.IO.Path]::IsPathRooted($EnvFile)) {
            $EnvFile
        }
        else {
            Join-Path $root $EnvFile
        }
    }
    else {
        Join-Path $root ".env"
    }
    if ($EnvFile -and -not (Test-Path -LiteralPath $resolvedEnvFile)) {
        throw "Compose environment file was not found: $resolvedEnvFile"
    }
    if (Test-Path -LiteralPath $resolvedEnvFile) {
        $compose += @("--env-file", $resolvedEnvFile)
    }
    $compose += @("-f", $composeFile)
    if ($FaultInjection) {
        $compose += @("--profile", "fault-injection")
    }

    $downArguments = @("down", "--remove-orphans")
    if ($RemoveVolumes) {
        $downArguments += "--volumes"
    }

    & docker @compose @downArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to stop the SUT."
    }
}
finally {
    Pop-Location
}
