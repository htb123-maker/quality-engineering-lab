[CmdletBinding()]
param(
    [ValidateRange(5, 600)]
    [int]$WaitSeconds = 60,

    [string]$ApiBaseUrl = "http://127.0.0.1:28000",

    [string]$PrometheusUrl = "http://127.0.0.1:29090",

    [string]$GrafanaUrl = "http://127.0.0.1:23000",

    [string]$TempoUrl = "http://127.0.0.1:23200",

    [string]$Output = "artifacts\performance\week27\observability.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "scripts\verify_observability.py"
$outputPath = if ([System.IO.Path]::IsPathRooted($Output)) {
    $Output
}
else {
    Join-Path $root $Output
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

& $python $script `
    --api-base-url $ApiBaseUrl `
    --prometheus-url $PrometheusUrl `
    --grafana-url $GrafanaUrl `
    --tempo-url $TempoUrl `
    --wait-seconds $WaitSeconds `
    --output $outputPath

exit $LASTEXITCODE
