"""Unit tests for typed settings."""

from pathlib import Path

import pytest
from qa_core.config.settings import Settings


def test_default_settings_are_local_and_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert str(settings.api_base_url) == "http://127.0.0.1:8000/"
    assert str(settings.appium_server_url) == "http://127.0.0.1:4723/"
    assert settings.postgres_dsn is None
    assert settings.redis_url is None
    assert settings.artifacts_dir == Path("artifacts")
    assert settings.log_level == "INFO"


def test_environment_variable_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QA_ENVIRONMENT", "ci")
    monkeypatch.setenv("QA_LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.environment == "ci"
    assert settings.log_level == "DEBUG"
