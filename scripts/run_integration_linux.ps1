[CmdletBinding()]
param(
    [string]$Image = "python:3.12-slim",
    [switch]$SkipSutStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$artifactsDir = Join-Path $root "artifacts\docker-integration"
$requirementsPath = Join-Path $artifactsDir "requirements.txt"

Push-Location $root

try {
    if (-not $SkipSutStart) {
        & (Join-Path $PSScriptRoot "start_sut.ps1")
    }

    New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null
    uv export --frozen --no-hashes --format requirements-txt |
        Set-Content -LiteralPath $requirementsPath -Encoding utf8

    $containerCommand = @(
        "pip install --disable-pip-version-check --root-user-action=ignore --quiet",
        "-r /workspace/artifacts/docker-integration/requirements.txt",
        "&& python -m pytest tests/integration tests/api -q -p no:cacheprovider",
        "--alluredir=/results"
    ) -join " "

    $dockerArgs = @(
        "run",
        "--rm",
        "--network",
        "quality-engineering-lab_default",
        "--user",
        "root",
        "-v",
        "${root}:/workspace:ro",
        "-v",
        "${artifactsDir}:/results",
        "-w",
        "/workspace",
        "-e",
        "PYTHONPATH=/workspace/packages",
        "-e",
        "QA_API_BASE_URL=http://api:8000",
        "-e",
        "QA_POSTGRES_DSN=postgresql://qa:qa@postgres:5432/qa",
        "-e",
        "QA_REDIS_URL=redis://redis:6379/0",
        $Image,
        "sh",
        "-lc",
        $containerCommand
    )

    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Linux container integration tests failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
