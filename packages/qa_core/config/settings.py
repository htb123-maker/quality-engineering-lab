"""Typed project configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "ci", "performance", "staging"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
AuthMode = Literal["bearer", "cookie"]


class Settings(BaseSettings):
    """Runtime settings shared by API, mobile, and performance tests."""

    model_config = SettingsConfigDict(
        env_prefix="QA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = "local"
    api_base_url: AnyHttpUrl = Field(
        default_factory=lambda: AnyHttpUrl("http://127.0.0.1:18000")
    )
    api_connect_timeout_seconds: float = Field(default=2.0, gt=0.0, le=120.0)
    api_read_timeout_seconds: float = Field(default=5.0, gt=0.0, le=120.0)
    api_write_timeout_seconds: float = Field(default=5.0, gt=0.0, le=120.0)
    api_pool_timeout_seconds: float = Field(default=2.0, gt=0.0, le=120.0)
    api_retry_max_attempts: int = Field(default=3, ge=1, le=10)
    api_retry_backoff_seconds: float = Field(default=0.25, ge=0.0, le=30.0)
    api_retry_max_backoff_seconds: float = Field(default=2.0, ge=0.0, le=120.0)
    api_retry_jitter_ratio: float = Field(default=0.2, ge=0.0, le=1.0)
    auth_mode: AuthMode = "bearer"
    auth_token_path: str = Field(default="/oauth/token", pattern=r"^/")
    auth_revoke_path: str = Field(default="/oauth/revoke", pattern=r"^/")
    auth_discovery_path: str = Field(
        default="/.well-known/openid-configuration",
        pattern=r"^/",
    )
    auth_refresh_skew_seconds: float = Field(default=30.0, ge=0.0, le=600.0)
    auth_test_username: str = Field(default="owner@atlas.example", min_length=1)
    auth_test_password: str = Field(default="local-test-password", min_length=1)
    appium_server_url: AnyHttpUrl = Field(
        default_factory=lambda: AnyHttpUrl("http://127.0.0.1:4723")
    )
    android_device_name: str = Field(default="Pixel_API_35_AOSP_ATD")
    android_udid: str = Field(default="emulator-5554")
    android_platform_version: str = Field(default="15")
    android_app_package: str = Field(default="com.android.fakesystemapp")
    android_app_activity: str = Field(
        default=".launcher.EmptyHomeActivity"
    )
    ios_device_name: str = Field(default="iPhone 16")
    ios_platform_version: str | None = Field(default=None)
    ios_udid: str | None = Field(default=None)
    ios_bundle_id: str = Field(default="com.apple.Preferences")
    ios_wda_local_port: int = Field(default=8100, ge=1, le=65535)
    ios_use_new_wda: bool = Field(default=True)
    ios_wda_launch_timeout_ms: int = Field(
        default=240_000,
        ge=10_000,
        le=600_000,
    )
    ios_wda_startup_retries: int = Field(default=2, ge=0, le=5)
    ios_wda_startup_retry_interval_ms: int = Field(
        default=10_000,
        ge=1_000,
        le=60_000,
    )
    postgres_dsn: PostgresDsn = Field(
        default_factory=lambda: PostgresDsn("postgresql://qa:qa@127.0.0.1:15432/qa")
    )
    redis_url: RedisDsn = Field(
        default_factory=lambda: RedisDsn("redis://127.0.0.1:16379/0")
    )
    artifacts_dir: Path = Field(default=Path("artifacts"))
    log_level: LogLevel = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one process-wide settings instance."""

    return Settings()
