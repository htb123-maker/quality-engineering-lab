[CmdletBinding()]
param(
    [ValidateRange(10, 600)]
    [int]$WaitSeconds = 120,

    [ValidateRange(30, 600)]
    [int]$DockerWaitSeconds = 180,

    [switch]$SkipBuild,

    [switch]$FaultInjection,

    [switch]$Monitoring,

    [string]$ProjectName = "",

    [string]$EnvFile = "",

    [string]$ApiBaseUrl = "http://127.0.0.1:18000",

    [string]$PostgresDsn = "postgresql://qa:qa@127.0.0.1:15432/qa",

    [string]$RedisUrl = "redis://127.0.0.1:26379/0"
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

$otelWasSet = Test-Path Env:QA_OTEL_ENABLED
$otelPreviousValue = $env:QA_OTEL_ENABLED

try {
    $compose = @("compose")
    if ($ProjectName) {
        $compose += @("-p", $ProjectName)
    }
    $resolvedEnvFile = if ($EnvFile) {
        if ([System.IO.Path]::IsPathRooted($EnvFile)) {
            $EnvFile
        }
        else {
            Join-Path $root $EnvFile
        }
    }
    else {
        Join-Path $root ".env"
    }
    if ($EnvFile -and -not (Test-Path -LiteralPath $resolvedEnvFile)) {
        throw "Compose environment file was not found: $resolvedEnvFile"
    }
    if (Test-Path -LiteralPath $resolvedEnvFile) {
        $compose += @("--env-file", $resolvedEnvFile)
    }
    $compose += @("-f", $composeFile)
    if ($FaultInjection) {
        $compose += @("--profile", "fault-injection")
    }
    if ($Monitoring) {
        $compose += @("--profile", "monitoring")
        $env:QA_OTEL_ENABLED = "1"
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

    & $python $checkScript `
        --wait-seconds $WaitSeconds `
        --api-base-url $ApiBaseUrl `
        --postgres-dsn $PostgresDsn `
        --redis-url $RedisUrl
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
    if ($otelWasSet) {
        $env:QA_OTEL_ENABLED = $otelPreviousValue
    }
    else {
        Remove-Item Env:QA_OTEL_ENABLED -ErrorAction SilentlyContinue
    }
    Pop-Location
}
