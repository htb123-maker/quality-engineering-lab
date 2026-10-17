# Week 1 Environment Recovery

## Purpose

Recover the Week 1 baseline when Docker Desktop has stopped, Appium is not
running, or a Python binary extension is blocked by Windows policy.

## Docker Desktop Is Unavailable

`scripts/start_sut.ps1` now starts Docker Desktop itself and waits for the Linux
engine before bringing up Compose:

```powershell
.\scripts\start_sut.ps1
```

Useful bounds:

```powershell
.\scripts\start_sut.ps1 -DockerWaitSeconds 180 -WaitSeconds 120
```

Expected signs:

```text
Docker engine is unavailable; starting Docker Desktop...
Docker engine is ready.
PASS API live: HTTP 200
PASS API ready: ...
PASS Namespace leftovers: test_namespaces=0
SUT ready: True
```

If Desktop cannot be found, install Docker Desktop or start it manually. The
script does not bypass system policy or modify Docker settings.

## Start Android and Appium

Start the emulator in a hidden window:

```powershell
Start-Process `
  -FilePath 'D:\Android\Sdk\emulator\emulator.exe' `
  -ArgumentList @(
    '-avd', 'Pixel_API_35_AOSP_ATD',
    '-no-window', '-no-audio', '-no-boot-anim', '-no-snapshot',
    '-port', '5554'
  ) `
  -WindowStyle Hidden

.\scripts\wait_for_android_ready.ps1 `
  -Serial emulator-5554 `
  -TimeoutSeconds 300
```

Start Appium with Java 21:

```powershell
.\scripts\start_appium.ps1 -Port 4723 -WaitSeconds 60
```

The launcher resolves `JAVA_HOME`, requires Java 17 or newer, writes logs under
`artifacts/`, waits for `/status`, and is idempotent when Appium is already
ready.

The `java` command in the user's PATH currently points to Corretto 8, while
`JAVA_HOME` points to the PyCharm JBR 21. Appium uses `JAVA_HOME`; the launcher
also prepends its Java bin directory for the Appium child process. Check the
effective values before changing system PATH:

```powershell
Write-Output $env:JAVA_HOME
& (Join-Path $env:JAVA_HOME 'bin\java.exe') -version
appium driver doctor uiautomator2
```

## Python Binary Extension Is Blocked

If `psycopg`, `mypy`, or another binary package raises:

```text
ImportError: DLL load failed ... 应用程序控制策略已阻止此文件
```

check Smart App Control and the package imports:

```powershell
Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' |
  Select-Object VerifiedAndReputablePolicyState

.\.venv\Scripts\python.exe -c "import psycopg, mypy; print('imports ok')"
```

Do not disable Smart App Control automatically. On 2026-10-18 the policy was
still enabled, but `psycopg 3.3.6`, `mypy 2.3.1`, and `pydantic_core` imported
successfully, and the local integration suite passed. If the block returns,
`scripts/check_sut.py` now reports an actionable PostgreSQL failure instead of
crashing at import time.

## Run the Week 1 Exit Checks

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy packages tests
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m pytest tests/integration -q
.\.venv\Scripts\python.exe scripts\run_smoke_matrix.py
.\.venv\Scripts\python.exe scripts\run_smoke_soak.py `
  --iterations 10 `
  --targets api android `
  --json-output artifacts\smoke-soak-week1-recheck.json `
  --allure-results artifacts\allure-results-week1-recheck
```

Generate the report:

```powershell
$env:ALLURE_NO_ANALYTICS='true'
allure generate artifacts\allure-results-week1-recheck `
  --clean -o artifacts\allure-report-week1-recheck
```

## PyCharm Debug Check

The project interpreter and pytest run configurations are present:

- SDK: `.venv\Scripts\python.exe`
- Run configurations: `Unit Tests`, `Smoke Tests`, `Android Tests`

Open `tests/unit/test_settings.py`, set a breakpoint in a test body, choose the
`Unit Tests` configuration, and use Debug. This last UI interaction remains a
manual check; command-line pytest success cannot prove that the IDE debugger UI
stops at a breakpoint.
