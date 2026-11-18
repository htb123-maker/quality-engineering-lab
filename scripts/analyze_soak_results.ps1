[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Profile,

    [Parameter(Mandatory)]
    [string]$Run,

    [string]$PrometheusUrl = "http://127.0.0.1:29090",

    [string]$Output = "artifacts\performance\week29\week29-soak\soak-analysis.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "scripts\analyze_soak_results.py"
$env:PYTHONPATH = "$(Join-Path $root 'packages');$root"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

$arguments = @(
    $script,
    "--profile", $Profile,
    "--run", $Run,
    "--prometheus-url", $PrometheusUrl,
    "--output", $Output
)

& $python @arguments
exit $LASTEXITCODE
