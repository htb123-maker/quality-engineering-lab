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
    postgres_dsn: PostgresDsn | None = Field(default=None)
    redis_url: RedisDsn | None = Field(default=None)
    artifacts_dir: Path = Field(default=Path("artifacts"))
    log_level: LogLevel = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one process-wide settings instance."""

    return Settings()
