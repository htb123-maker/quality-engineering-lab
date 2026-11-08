[CmdletBinding()]
param(
    [switch]$RemoveVolumes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$localEnvFile = Join-Path $root ".env.performance"
$envFile = if (Test-Path -LiteralPath $localEnvFile) {
    $localEnvFile
}
else {
    Join-Path $root ".env.performance.example"
}

& (Join-Path $PSScriptRoot "stop_sut.ps1") `
    -RemoveVolumes:$RemoveVolumes `
    -ProjectName "quality-engineering-lab-performance" `
    -EnvFile $envFile
