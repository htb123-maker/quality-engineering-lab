"""Unit tests for typed settings."""

from pathlib import Path

import pytest
from qa_core.config.settings import Settings


def test_default_settings_are_local_and_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert str(settings.api_base_url) == "http://127.0.0.1:18000/"
    assert settings.api_connect_timeout_seconds == 2.0
    assert settings.api_read_timeout_seconds == 5.0
    assert settings.api_write_timeout_seconds == 5.0
    assert settings.api_pool_timeout_seconds == 2.0
    assert settings.api_retry_max_attempts == 3
    assert settings.api_retry_backoff_seconds == 0.25
    assert settings.api_retry_max_backoff_seconds == 2.0
    assert settings.api_retry_jitter_ratio == 0.2
    assert settings.auth_mode == "bearer"
    assert settings.auth_token_path == "/oauth/token"
    assert settings.auth_revoke_path == "/oauth/revoke"
    assert settings.auth_discovery_path == "/.well-known/openid-configuration"
    assert settings.auth_refresh_skew_seconds == 30.0
    assert settings.auth_test_username == "owner@atlas.example"
    assert settings.auth_test_password == "local-test-password"
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
    monkeypatch.setenv("QA_API_CONNECT_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("QA_API_RETRY_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("QA_AUTH_MODE", "cookie")
    monkeypatch.setenv("QA_AUTH_REFRESH_SKEW_SECONDS", "5")

    settings = Settings(_env_file=None)

    assert settings.environment == "ci"
    assert settings.log_level == "DEBUG"
    assert settings.api_connect_timeout_seconds == 1.5
    assert settings.api_retry_max_attempts == 4
    assert settings.auth_mode == "cookie"
    assert settings.auth_refresh_skew_seconds == 5.0
