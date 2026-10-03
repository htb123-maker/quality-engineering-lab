[CmdletBinding()]
param(
    [string]$User = "qa",
    [string]$Database = "qa"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $root "apps\compose\compose.yaml"
$verifySql = Join-Path $root "apps\compose\postgres\verify_day05.sql"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop with the Compose plugin first."
}

Push-Location $root

try {
    $compose = @("compose")
    $envFile = Join-Path $root ".env"
    if (Test-Path -LiteralPath $envFile) {
        $compose += @("--env-file", $envFile)
    }
    $compose += @("-f", $composeFile)

    Get-Content -Raw -LiteralPath $verifySql |
        & docker @compose exec -T postgres `
            psql -U $User -d $Database -v ON_ERROR_STOP=1 -X

    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL schema and seed verification failed."
    }
}
finally {
    Pop-Location
}
