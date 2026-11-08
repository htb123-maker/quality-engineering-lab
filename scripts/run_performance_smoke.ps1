[CmdletBinding()]
param(
    [string]$Profile = "configs\performance-smoke.yaml",
    [string]$ArtifactDir = "artifacts\performance\week25",

    [switch]$StartSut,
    [switch]$Overwrite
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$locustFile = Join-Path $root "performance\locustfiles\api_journeys.py"
$profilePath = if ([System.IO.Path]::IsPathRooted($Profile)) {
    $Profile
}
else {
    Join-Path $root $Profile
}
$artifactDir = if ([System.IO.Path]::IsPathRooted($ArtifactDir)) {
    $ArtifactDir
}
else {
    Join-Path $root $ArtifactDir
}
$csvPrefix = Join-Path $artifactDir "smoke"
$htmlReport = Join-Path $artifactDir "smoke.html"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}
if (-not (Test-Path -LiteralPath $profilePath)) {
    throw "Performance profile was not found: $profilePath"
}
if ((Test-Path -LiteralPath $htmlReport) -and -not $Overwrite) {
    throw "Performance artifacts already exist. Pass -Overwrite to replace them."
}

if ($StartSut) {
    & (Join-Path $PSScriptRoot "start_performance_sut.ps1")
}

New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null

$env:PYTHONPATH = "$(Join-Path $root 'packages');$root"
$env:QA_PERF_PROFILE = $profilePath

Push-Location $root

try {
    & $python -m locust `
        -f $locustFile `
        --headless `
        --only-summary `
        --csv $csvPrefix `
        --csv-full-history `
        --html $htmlReport `
        --exit-code-on-error 1
    if ($LASTEXITCODE -ne 0) {
        throw "Performance smoke failed or missed an SLO. See $artifactDir."
    }
}
finally {
    Pop-Location
}
