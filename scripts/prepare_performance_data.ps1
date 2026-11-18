[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$RunId,

    [string]$WorkspaceSlug,
    [int]$ItemCount = 100,
    [int]$AccountCount = 16,
    [string]$EnvFile = ".env.performance.example"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONPATH = "$(Join-Path $root 'packages');$root"
$envPath = if ([System.IO.Path]::IsPathRooted($EnvFile)) {
    $EnvFile
}
else {
    Join-Path $root $EnvFile
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

$arguments = @(
    (Join-Path $root "scripts\prepare_performance_data.py"),
    "--run-id", $RunId,
    "--item-count", $ItemCount,
    "--account-count", $AccountCount,
    "--env-file", $envPath
)
if ($WorkspaceSlug) {
    $arguments += @("--workspace-slug", $WorkspaceSlug)
}

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Performance dataset provisioning failed."
}
