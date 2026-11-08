[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$DataFile,

    [Parameter(Mandatory)]
    [string]$OutputDir,

    [Parameter(Mandatory)]
    [string]$RunId,

    [string]$Profile = "configs\performance-distributed-smoke.yaml",
    [ValidateSet("local", "master", "worker")]
    [string]$Role = "local",
    [int]$ExpectedWorkers = 1,
    [string]$MasterHost = "127.0.0.1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONPATH = "$(Join-Path $root 'packages');$root"
$profilePath = if ([System.IO.Path]::IsPathRooted($Profile)) {
    $Profile
}
else {
    Join-Path $root $Profile
}
$dataPath = if ([System.IO.Path]::IsPathRooted($DataFile)) {
    $DataFile
}
else {
    Join-Path $root $DataFile
}
$outputPath = if ([System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir
}
else {
    Join-Path $root $OutputDir
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

& $python (Join-Path $root "scripts\run_distributed_locust.py") `
    --profile $profilePath `
    --data-file $dataPath `
    --output-dir $outputPath `
    --run-id $RunId `
    --role $Role `
    --expected-workers $ExpectedWorkers `
    --master-host $MasterHost
if ($LASTEXITCODE -ne 0) {
    throw "Distributed Locust run failed."
}
