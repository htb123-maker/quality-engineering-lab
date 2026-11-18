[CmdletBinding()]
param(
    [string]$EnvFile = ".env.performance.example",

    [string]$Output = "artifacts\performance\week29\week29-soak\database-cache-diagnostics.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "scripts\collect_database_cache_diagnostics.py"
$env:PYTHONPATH = "$(Join-Path $root 'packages');$root"
$envPath = if ([System.IO.Path]::IsPathRooted($EnvFile)) {
    $EnvFile
}
else {
    Join-Path $root $EnvFile
}
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
    --env-file $envPath `
    --output $outputPath
exit $LASTEXITCODE
