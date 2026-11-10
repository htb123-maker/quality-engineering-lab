[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Profile,

    [Parameter(Mandatory)]
    [string]$Label,

    [Parameter(Mandatory)]
    [string]$OutputDir,

    [string]$DataFile,
    [int]$WarmupSeconds = 15,
    [int]$MeasuredRuns = 3
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
$outputPath = if ([System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir
}
else {
    Join-Path $root $OutputDir
}
$dataPath = if ($DataFile) {
    if ([System.IO.Path]::IsPathRooted($DataFile)) {
        $DataFile
    }
    else {
        Join-Path $root $DataFile
    }
}
else {
    $null
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

$arguments = @(
    (Join-Path $root "scripts\run_performance_profile.py"),
    "--profile", $profilePath,
    "--label", $Label,
    "--output-dir", $outputPath,
    "--warmup-seconds", $WarmupSeconds,
    "--measured-runs", $MeasuredRuns
)
if ($dataPath) {
    $arguments += @("--data-file", $dataPath)
}

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Performance profile failed or missed an SLO."
}
