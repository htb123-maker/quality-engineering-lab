[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$RunId,

    [string]$WorkspaceSlug,
    [string]$EnvFile = ".env.performance.example",
    [string]$OutputRoot = "artifacts\performance\week26"
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
$outputPath = if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    $OutputRoot
}
else {
    Join-Path $root $OutputRoot
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

$arguments = @(
    (Join-Path $root "scripts\cleanup_performance_data.py"),
    "--run-id", $RunId,
    "--env-file", $envPath,
    "--output-root", $outputPath
)
if ($WorkspaceSlug) {
    $arguments += @("--workspace-slug", $WorkspaceSlug)
}

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Performance dataset cleanup failed."
}
