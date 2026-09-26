[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 999)]
    [int]$Day,

    [string]$Title = "",

    [string]$Notes = "",

    [switch]$SkipChecks,

    [switch]$NoCommit,

    [switch]$NoPr,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$dayId = "DAY-{0:D2}" -f $Day
$dayTitle = if ([string]::IsNullOrWhiteSpace($Title)) { "Day $Day Completion" } else { $Title }
$reportDir = Join-Path $root "reports\daily"
$reportPath = Join-Path $reportDir "$dayId.md"

Push-Location $root

try {
    $branch = (git branch --show-current).Trim()
    $baseCommit = (git rev-parse --short HEAD).Trim()
    $remoteUrl = git remote get-url origin 2>$null
    $hasRemote = -not [string]::IsNullOrWhiteSpace($remoteUrl)

    $checks = @()
    $failed = $false

    function Invoke-QualityCheck {
        param(
            [string]$Name,
            [scriptblock]$Command
        )

        $output = & $Command 2>&1 | Out-String
        $passed = $LASTEXITCODE -eq 0
        $script:failed = $script:failed -or (-not $passed)

        return [pscustomobject]@{
            Name = $Name
            Passed = $passed
            Output = $output.Trim()
        }
    }

    if (-not $SkipChecks) {
        $python = Join-Path $root ".venv\Scripts\python.exe"
        $checks += Invoke-QualityCheck "Ruff" { & $python -m ruff check . }
        $checks += Invoke-QualityCheck "Mypy" { & $python -m mypy packages tests }
        $checks += Invoke-QualityCheck "Pytest" {
            & $python -m pytest -q --alluredir=artifacts/allure-results
        }
        $checks += Invoke-QualityCheck "Allure report" {
            $env:ALLURE_NO_ANALYTICS = "true"
            allure generate artifacts/allure-results --clean -o artifacts/allure-report
        }
    }

    $statusLines = (git status --short | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($statusLines)) {
        $statusLines = "No uncommitted changes before report generation."
    }

    $checkRows = if ($checks.Count -eq 0) {
        "| Check | Status |`n| --- | --- |`n| Checks skipped | SKIP |"
    } else {
        ($checks | ForEach-Object {
            $status = if ($_.Passed) { "PASS" } else { "FAIL" }
            "| $($_.Name) | $status |"
        }) -join "`n"
    }

    $checkDetails = if ($checks.Count -eq 0) {
        "Quality checks were skipped."
    } else {
        ($checks | ForEach-Object {
            "### $($_.Name)`n`n``````text`n$($_.Output)`n``````"
        }) -join "`n`n"
    }

    $report = @"
# $dayId - $dayTitle

- Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")
- Branch: $branch
- Base commit: $baseCommit
- Remote: $(if ($hasRemote) { $remoteUrl } else { "not configured" })

## Completion status

$(if ($failed) { "FAILED: one or more quality checks did not pass." } else { "PASSED: automated quality checks completed." })

## Quality checks

| Check | Status |
| --- | --- |
$checkRows

## Workspace before report generation

``````text
$statusLines
``````

## Notes

$Notes

## Command output

$checkDetails

## Follow-up

- Unchecked items must be recorded explicitly before this day is considered complete.
- Do not close defects or approve releases automatically.
"@

    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
        Set-Content -LiteralPath $reportPath -Value $report -Encoding utf8
    }

    if ($failed) {
        throw "Day $Day quality checks failed. Review $reportPath."
    }

    if ($NoCommit -or $DryRun) {
        Write-Host "Report generated at $reportPath"
        return
    }

    git add .
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        git commit -m "docs(day-$Day): add completion report"
    } else {
        Write-Host "No changes to commit."
    }

    if ($NoPr -or -not $hasRemote) {
        if (-not $hasRemote) {
            Write-Host "Origin remote is not configured. PR creation skipped."
        }
        return
    }

    $defaultBranch = "main"
    $currentBranch = (git branch --show-current).Trim()
    if ($currentBranch -eq $defaultBranch) {
        $prBranch = "study/day-$($Day.ToString("D2"))"
        git show-ref --verify --quiet "refs/heads/$prBranch"
        if ($LASTEXITCODE -eq 0) {
            git switch $prBranch
        } else {
            git switch -c $prBranch
        }
    }

    $prBranch = (git branch --show-current).Trim()
    git push -u origin $prBranch

    gh auth status *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "gh is not authenticated. Branch pushed, but PR creation was skipped."
        return
    }

    $existingPr = gh pr list --head $prBranch --json number --jq ".[0].number"
    if (-not [string]::IsNullOrWhiteSpace($existingPr)) {
        Write-Host "PR #$existingPr already exists for $prBranch."
        return
    }

    gh pr create `
        --base $defaultBranch `
        --head $prBranch `
        --title "Study ${dayId}: $dayTitle" `
        --body-file $reportPath
}
finally {
    Pop-Location
}
