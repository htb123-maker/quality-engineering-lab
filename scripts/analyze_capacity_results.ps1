[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$StressProfile,

    [Parameter(Mandatory)]
    [string]$StressRun,

    [Parameter(Mandatory)]
    [string]$SpikeProfile,

    [Parameter(Mandatory)]
    [string]$SpikeRun,

    [string]$PrometheusUrl = "http://127.0.0.1:29090",

    [string]$Output = "artifacts\performance\week28\week28-capacity\capacity-analysis.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "scripts\analyze_capacity_results.py"
$env:PYTHONPATH = "$(Join-Path $root 'packages');$root"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

$arguments = @(
    $script,
    "--stress-profile", $StressProfile,
    "--stress-run", $StressRun,
    "--spike-profile", $SpikeProfile,
    "--spike-run", $SpikeRun,
    "--prometheus-url", $PrometheusUrl,
    "--output", $Output
)

& $python @arguments
exit $LASTEXITCODE
