[CmdletBinding()]
param(
    [int]$Workers = 4,
    [switch]$SkipLeftoverCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$baseTemp = Join-Path $root "artifacts\pytest-tmp"

Push-Location $root

try {
    & $python -m pytest tests\api -q -p no:cacheprovider `
        -n $Workers --basetemp=$baseTemp
    if ($LASTEXITCODE -ne 0) {
        throw "Parallel API tests failed with exit code $LASTEXITCODE."
    }

    if (-not $SkipLeftoverCheck) {
        & $python scripts\check_sut.py
        if ($LASTEXITCODE -ne 0) {
            throw "Leftover check failed with exit code $LASTEXITCODE."
        }
    }
}
finally {
    Pop-Location
}
