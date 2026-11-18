[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Serial,

    [string]$Package = "com.example.qaweek15",
    [string]$Activity = ".MainActivity",

    [ValidateRange(1, 50)]
    [int]$ColdRuns = 10,

    [ValidateRange(1, 50)]
    [int]$WarmRuns = 10,

    [ValidateRange(10, 500)]
    [int]$Taps = 40,

    [string]$Output =
        "artifacts\performance\week30\android\mobile-performance.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "scripts\collect_android_mobile_performance.py"
$env:PYTHONPATH = "$(Join-Path $root 'packages');$root"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

$arguments = @(
    $script,
    "--serial", $Serial,
    "--package", $Package,
    "--activity", $Activity,
    "--cold-runs", "$ColdRuns",
    "--warm-runs", "$WarmRuns",
    "--taps", "$Taps",
    "--output", $Output
)

& $python @arguments
exit $LASTEXITCODE
