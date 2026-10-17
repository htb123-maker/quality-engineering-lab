[CmdletBinding()]
param(
    [ValidateRange(10, 600)]
    [int]$WaitSeconds = 120,

    [ValidateRange(30, 600)]
    [int]$DockerWaitSeconds = 180,

    [switch]$SkipBuild,

    [switch]$FaultInjection
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

function Start-DockerDesktopIfNeeded {
    & docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    $candidates = @(
        'C:\Program Files\Docker\Docker\Docker Desktop.exe',
        (Join-Path $env:LOCALAPPDATA 'Docker\Docker Desktop.exe')
    )
    $desktop = $candidates | Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if (-not $desktop) {
        throw "Docker daemon is unavailable and Docker Desktop was not found."
    }

    Write-Host "Docker engine is unavailable; starting Docker Desktop..." `
        -ForegroundColor Yellow
    Start-Process -FilePath $desktop -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds($DockerWaitSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Docker engine is ready." -ForegroundColor Green
            return
        }
    }
    throw "Docker engine did not become ready within $DockerWaitSeconds seconds."
}

Push-Location $root

try {
    $compose = @("compose")
    $envFile = Join-Path $root ".env"
    if (Test-Path -LiteralPath $envFile) {
        $compose += @("--env-file", $envFile)
    }
    $compose += @("-f", $composeFile)
    if ($FaultInjection) {
        $compose += @("--profile", "fault-injection")
    }

    & docker @compose config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose configuration is invalid."
    }

    Start-DockerDesktopIfNeeded

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
