"""Smoke tests for the Day 2 execution environment."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import sys
from pathlib import Path

import allure
import pytest
from qa_core.config.settings import Settings


@allure.epic("Quality Engineering Lab")
@allure.feature("Environment baseline")
@allure.story("Python runtime")
@pytest.mark.smoke
def test_project_uses_python_312_virtual_environment(project_root: Path) -> None:
    if sys.platform == "win32":
        expected_python = project_root / ".venv" / "Scripts" / "python.exe"
    else:
        expected_python = project_root / ".venv" / "bin" / "python"

    assert sys.version_info[:2] == (3, 12)
    assert Path(sys.executable).resolve() == expected_python.resolve()


@allure.epic("Quality Engineering Lab")
@allure.feature("Environment baseline")
@allure.story("Typed configuration")
@pytest.mark.smoke
def test_typed_settings_load_without_external_services() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert str(settings.api_base_url).startswith("http://127.0.0.1")
    assert str(settings.appium_server_url).startswith("http://127.0.0.1")
