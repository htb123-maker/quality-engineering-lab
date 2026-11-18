[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$BaselineDir,

    [Parameter(Mandatory)]
    [string]$LoadDir,

    [Parameter(Mandatory)]
    [string]$OutputDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONPATH = "$(Join-Path $root 'packages');$root"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

& $python (Join-Path $root "scripts\compare_performance_runs.py") `
    --baseline-dir $BaselineDir `
    --load-dir $LoadDir `
    --output-dir $OutputDir
if ($LASTEXITCODE -ne 0) {
    throw "Performance comparison failed."
}
