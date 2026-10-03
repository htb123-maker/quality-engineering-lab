[CmdletBinding()]
param(
    [ValidateRange(10, 600)]
    [int]$WaitSeconds = 120,

    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $root "apps\compose\compose.yaml"
$python = Join-Path $root ".venv\Scripts\python.exe"
$checkScript = Join-Path $root "scripts\check_sut.py"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop with the Compose plugin first."
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found. Run 'uv sync' first."
}

Push-Location $root

try {
    $compose = @("compose")
    $envFile = Join-Path $root ".env"
    if (Test-Path -LiteralPath $envFile) {
        $compose += @("--env-file", $envFile)
    }
    $compose += @("-f", $composeFile)

    & docker @compose config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose configuration is invalid."
    }

    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon is unavailable. Start Docker Desktop and retry."
    }

    $upArguments = @("up", "--detach", "--wait", "--wait-timeout", $WaitSeconds)
    if (-not $SkipBuild) {
        $upArguments += "--build"
    }

    & docker @compose @upArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to start the SUT."
    }

    & $python $checkScript --wait-seconds $WaitSeconds
    if ($LASTEXITCODE -ne 0) {
        throw "The SUT started, but readiness checks failed."
    }
}
catch {
    Write-Host "Collecting Compose diagnostics..." -ForegroundColor Yellow
    & docker @compose ps
    & docker @compose logs --no-color --tail 100
    throw
}
finally {
    Pop-Location
}
