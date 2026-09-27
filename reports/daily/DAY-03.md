# DAY-03 - Android Appium Environment and Minimal Session

- Date: 2026-09-27 00:19:21 +08:00
- Branch: main
- Base commit: edb7c18
- Day commit: 90ba602
- Remote: not configured

## Completion status

PASSED: automated quality checks completed.

## Quality checks

| Check | Status |
| --- | --- |
| Ruff | PASS |
| Mypy | PASS |
| Pytest | PASS |
| Allure report | PASS |

## Acceptance method

Precondition: start the AVD and Appium Server before running the Android test:

```powershell
& 'D:\Android\Sdk\emulator\emulator.exe' -avd Pixel_API_35_AOSP_ATD -no-window -no-audio -no-boot-anim -no-snapshot
appium --address 127.0.0.1 --port 4723 --log-level debug
```

Run the following commands:

```powershell
git status --short --branch
& 'D:\Android\Sdk\platform-tools\adb.exe' -s emulator-5554 shell getprop sys.boot_completed
Invoke-RestMethod -Uri 'http://127.0.0.1:4723/status' -TimeoutSec 5
uv run --no-sync pytest tests/android -q --alluredir=artifacts/allure-results
uv run --no-sync pytest -q
```

Expected results:

```text
Git worktree clean
sys.boot_completed = 1
Appium /status ready = true
Android test: 1 passed
Full suite: 5 passed
```

Evidence:

- `artifacts/allure-report/index.html`
- `artifacts/emulator.out.log`
- `artifacts/appium-server.out.log`

## Deliverables

- Android driver factory in `packages/qa_core/driver/android.py`.
- Android Session smoke test in `tests/android/test_session.py`.
- Android settings and environment template updates.
- Appium and Selenium dependencies recorded in `pyproject.toml` and `uv.lock`.
- Android 35 AOSP ATD emulator and Appium 2.19 Server verified online.
- Allure HTML report generated under `artifacts/allure-report`.

## Notes

Installed Android 35 AOSP ATD environment, Appium 2.19.0, UiAutomator2 4.2.9, Appium Python Client 5.3.1, and verified a real Android session. Network instability required verified-wheel fallback for Python dependencies.

Temporary SDK archives, metadata, and local wheel mirrors were removed before
the clean Day 3 commit. The `.tmp-*` pattern is ignored to prevent recurrence.

## Command output

### Ruff

```text
All checks passed!
```

### Mypy

```text
Success: no issues found in 13 source files
```

### Pytest

```text
.....                                                                    [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\_pytest\cacheprovider.py:475
  D:\Codex projects\Appium 2 study\.venv\Lib\site-packages\_pytest\cacheprovider.py:475: PytestCacheWarning: could not create cache path D:\Codex projects\Appium 2 study\.pytest_cache\v\cache\nodeids: [WinError 5] �ܾ����ʡ�: 'D:\\Codex projects\\Appium 2 study\\.pytest_cache\\v\\cache'
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
5 passed, 1 warning in 2.25s
```

### Allure report

```text
Report successfully generated to artifacts\allure-report
```

## Follow-up

- Unchecked items must be recorded explicitly before this day is considered complete.
- Do not close defects or approve releases automatically.
