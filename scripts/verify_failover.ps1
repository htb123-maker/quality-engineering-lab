[CmdletBinding()]
param(
    [string]$ApiBaseUrl = "http://127.0.0.1:28000",

    [string]$Project = "quality-engineering-lab-performance",

    [string[]]$Service = @("redis", "postgres", "api"),

    [ValidateRange(5, 300)]
    [int]$WaitSeconds = 90,

    [string]$Output = "artifacts\performance\week29\week29-soak\failover.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "scripts\verify_failover.py"
$composeFile = Join-Path $root "apps\compose\compose.yaml"
$envFile = Join-Path $root ".env.performance.example"
$outputPath = if ([System.IO.Path]::IsPathRooted($Output)) {
    $Output
}
else {
    Join-Path $root $Output
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

$arguments = @(
    $script,
    "--api-base-url", $ApiBaseUrl,
    "--project", $Project,
    "--compose-file", $composeFile,
    "--env-file", $envFile,
    "--wait-seconds", $WaitSeconds,
    "--output", $outputPath
)
foreach ($value in $Service) {
    $arguments += @("--service", $value)
}

& $python @arguments
exit $LASTEXITCODE
