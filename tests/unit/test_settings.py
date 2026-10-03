"""Unit tests for typed settings."""

from pathlib import Path

import pytest
from qa_core.config.settings import Settings


def test_default_settings_are_local_and_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert str(settings.api_base_url) == "http://127.0.0.1:18000/"
    assert str(settings.appium_server_url) == "http://127.0.0.1:4723/"
    assert settings.ios_device_name == "iPhone 16"
    assert settings.ios_platform_version is None
    assert settings.ios_udid is None
    assert settings.ios_bundle_id == "com.apple.Preferences"
    assert settings.ios_wda_local_port == 8100
    assert settings.ios_use_new_wda is True
    assert settings.ios_wda_launch_timeout_ms == 240_000
    assert settings.ios_wda_startup_retries == 2
    assert settings.ios_wda_startup_retry_interval_ms == 10_000
    assert str(settings.postgres_dsn) == "postgresql://qa:qa@127.0.0.1:15432/qa"
    assert str(settings.redis_url) == "redis://127.0.0.1:16379/0"
    assert settings.artifacts_dir == Path("artifacts")
    assert settings.log_level == "INFO"


def test_environment_variable_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QA_ENVIRONMENT", "ci")
    monkeypatch.setenv("QA_LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.environment == "ci"
    assert settings.log_level == "DEBUG"
