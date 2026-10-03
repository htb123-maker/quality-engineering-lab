[CmdletBinding()]
param(
    [switch]$RemoveVolumes
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
    $envFile = Join-Path $root ".env"
    if (Test-Path -LiteralPath $envFile) {
        $compose += @("--env-file", $envFile)
    }
    $compose += @("-f", $composeFile)

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
