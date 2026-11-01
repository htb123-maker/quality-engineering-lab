[CmdletBinding()]
param(
    [ValidateRange(10, 600)]
    [int]$WaitSeconds = 120,

    [switch]$SkipBuild
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

& (Join-Path $PSScriptRoot "start_sut.ps1") `
    -WaitSeconds $WaitSeconds `
    -SkipBuild:$SkipBuild `
    -ProjectName "quality-engineering-lab-performance" `
    -EnvFile $envFile `
    -ApiBaseUrl "http://127.0.0.1:28000" `
    -PostgresDsn "postgresql://qa:qa@127.0.0.1:25432/qa" `
    -RedisUrl "redis://127.0.0.1:36379/0"
