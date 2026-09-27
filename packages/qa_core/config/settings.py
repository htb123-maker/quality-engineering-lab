"""Typed project configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "ci", "performance", "staging"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


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
        default_factory=lambda: AnyHttpUrl("http://127.0.0.1:8000")
    )
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
    postgres_dsn: PostgresDsn | None = Field(default=None)
    redis_url: RedisDsn | None = Field(default=None)
    artifacts_dir: Path = Field(default=Path("artifacts"))
    log_level: LogLevel = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one process-wide settings instance."""

    return Settings()
