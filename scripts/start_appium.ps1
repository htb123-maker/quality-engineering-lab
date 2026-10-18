[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 4723,

    [ValidateRange(10, 300)]
    [int]$WaitSeconds = 60,

    [ValidateSet("debug", "info", "warn", "error")]
    [string]$LogLevel = "info"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$artifacts = Join-Path $root "artifacts"
$stdoutLog = Join-Path $artifacts "appium-server.out.log"
$stderrLog = Join-Path $artifacts "appium-server.err.log"

function Test-JavaMajorVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$JavaExecutable
    )

    $versionLine = (& $JavaExecutable -version 2>&1 | Select-Object -First 1).ToString()
    if ($versionLine -match 'version "(?<major>\d+)') {
        return [int]$Matches.major
    }
    return 0
}

function Resolve-JavaHome {
    $candidates = @($env:JAVA_HOME)
    $candidates += @(
        'D:\python charm\PyCharm 2025.3\jbr',
        (Join-Path $env:USERPROFILE '.jdks\openjdk-25.0.1')
    )

    foreach ($candidate in $candidates) {
        if (-not $candidate) {
            continue
        }
        $java = Join-Path $candidate "bin\java.exe"
        if ((Test-Path -LiteralPath $java) -and (Test-JavaMajorVersion $java) -ge 17) {
            return $candidate
        }
    }
    throw "No JDK 17+ found. Set JAVA_HOME to a compatible JDK."
}

function Test-AppiumReady {
    param(
        [Parameter(Mandatory = $true)]
        [int]$TargetPort
    )

    try {
        $status = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$TargetPort/status" `
            -TimeoutSec 2
        return [bool]$status.value.ready
    }
    catch {
        return $false
    }
}

$appiumCommand = Get-Command appium.cmd -ErrorAction SilentlyContinue
if (-not $appiumCommand) {
    throw "Appium CLI was not found in PATH."
}

$javaHome = Resolve-JavaHome
$env:JAVA_HOME = $javaHome
$env:Path = "$(Join-Path $javaHome 'bin');$env:Path"
$javaMajor = Test-JavaMajorVersion (Join-Path $javaHome "bin\java.exe")
Write-Host "Using JAVA_HOME=$javaHome (Java $javaMajor)"

if (Test-AppiumReady -TargetPort $Port) {
    Write-Host "Appium is already ready on port $Port." -ForegroundColor Green
    return
}

$listener = Get-NetTCPConnection `
    -State Listen `
    -LocalPort $Port `
    -ErrorAction SilentlyContinue
if ($listener) {
    throw "Port $Port is already in use by process $($listener.OwningProcess)."
}

New-Item -ItemType Directory -Path $artifacts -Force | Out-Null
$appium = $appiumCommand.Source
$arguments = @(
    "--address", "127.0.0.1",
    "--port", $Port,
    "--log-level", $LogLevel,
    "--allow-insecure", "chromedriver_autodownload"
)

Start-Process `
    -FilePath $appium `
    -ArgumentList $arguments `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog | Out-Null

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-AppiumReady -TargetPort $Port) {
        Write-Host "Appium is ready on port $Port." -ForegroundColor Green
        return
    }
    Start-Sleep -Seconds 1
}

throw "Appium did not become ready within $WaitSeconds seconds. See $stdoutLog and $stderrLog."
