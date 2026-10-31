"""Typed project configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "ci", "performance", "staging"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
AuthMode = Literal["bearer", "cookie"]
IosDeviceProvider = Literal["local", "browserstack", "saucelabs", "lambdatest"]
IosCapabilityProfile = Literal["simulator", "device"]


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
    toxiproxy_url: AnyHttpUrl = Field(
        default_factory=lambda: AnyHttpUrl("http://127.0.0.1:18474")
    )
    toxiproxy_timeout_seconds: float = Field(default=2.0, gt=0.0, le=30.0)
    toxiproxy_proxy_port_base: int = Field(default=18100, ge=1024, le=65531)
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
    auth_issuer: str = Field(
        default="quality-engineering-lab-local",
        min_length=1,
    )
    auth_jwt_secret: str = Field(
        default="local-sut-jwt-secret-not-for-production",
        min_length=1,
    )
    rate_limit_write_max: int = Field(default=20, ge=0, le=10_000)
    rate_limit_write_window_seconds: float = Field(
        default=60.0,
        gt=0.0,
        le=3600.0,
    )
    rate_limit_principal_max: int = Field(default=40, ge=0, le=100_000)
    auth_signin_failure_max: int = Field(default=10, ge=0, le=1000)
    auth_signin_failure_window_seconds: float = Field(
        default=60.0,
        gt=0.0,
        le=3600.0,
    )
    max_request_bytes: int = Field(default=65_536, ge=1024, le=10_485_760)
    appium_server_url: AnyHttpUrl = Field(
        default_factory=lambda: AnyHttpUrl("http://127.0.0.1:4723")
    )
    android_device_name: str = Field(default="Pixel_API_35_AOSP_ATD")
    android_udid: str = Field(default="emulator-5554")
    android_platform_version: str = Field(default="15")
    android_device_matrix: Path = Field(
        default=Path("configs/android-device-matrix.yaml")
    )
    android_app_package: str = Field(default="com.android.fakesystemapp")
    android_app_activity: str = Field(
        default=".launcher.EmptyHomeActivity"
    )
    android_adb_exec_timeout_ms: int = Field(
        default=60_000,
        ge=10_000,
        le=300_000,
    )
    android_new_command_timeout_seconds: int = Field(default=300, ge=0, le=3600)
    android_system_port: int = Field(default=8200, ge=1024, le=65535)
    android_mjpeg_server_port: int = Field(default=7810, ge=1024, le=65535)
    android_ui_wait_timeout_seconds: float = Field(default=10.0, gt=0.0, le=120.0)
    android_ui_wait_poll_seconds: float = Field(default=0.25, gt=0.0, le=10.0)
    ios_device_name: str = Field(default="iPhone 16")
    ios_platform_version: str | None = Field(default=None)
    ios_udid: str | None = Field(default=None)
    ios_bundle_id: str = Field(default="com.apple.Preferences")
    ios_xcode_org_id: str | None = Field(default=None)
    ios_xcode_signing_id: str = Field(default="Apple Development")
    ios_updated_wda_bundle_id: str | None = Field(default=None)
    ios_allow_provisioning_updates: bool = Field(default=False)
    ios_show_xcode_log: bool = Field(default=False)
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
    ios_device_provider: IosDeviceProvider = "local"
    ios_capability_profile: IosCapabilityProfile = "simulator"
    ios_cloud_remote_url: AnyHttpUrl | None = None
    ios_cloud_user: str | None = None
    ios_cloud_access_key: SecretStr | None = None
    ios_cloud_app: str | None = None
    ios_cloud_device_name: str = Field(default="iPhone 15", min_length=1)
    ios_cloud_platform_version: str = Field(default="17", min_length=1)
    ios_cloud_project_name: str = Field(
        default="quality-engineering-lab",
        min_length=1,
    )
    ios_cloud_build_name: str = Field(default="ios-cloud-smoke", min_length=1)
    ios_cloud_session_name: str = Field(
        default="ios-session-smoke",
        min_length=1,
    )
    postgres_dsn: PostgresDsn = Field(
        default_factory=lambda: PostgresDsn("postgresql://qa:qa@127.0.0.1:15432/qa")
    )
    postgres_max_connections: int = Field(default=16, ge=1, le=10_000)
    postgres_connection_timeout_seconds: float = Field(
        default=2.0,
        gt=0.0,
        le=120.0,
    )
    redis_url: RedisDsn = Field(
        default_factory=lambda: RedisDsn("redis://127.0.0.1:26379/0")
    )
    catalog_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)
    catalog_cache_negative_ttl_seconds: int = Field(default=10, ge=1, le=3600)
    job_ttl_seconds: int = Field(default=900, ge=10, le=86_400)
    job_worker_poll_seconds: float = Field(default=0.25, gt=0.0, le=30.0)
    job_worker_enabled: bool = True
    ws_subscriber_queue_size: int = Field(default=64, ge=1, le=10_000)
    artifacts_dir: Path = Field(default=Path("artifacts"))
    log_level: LogLevel = Field(default="INFO")

    @model_validator(mode="after")
    def validate_android_ui_wait(self) -> Self:
        """Keep the explicit-wait poll interval within its deadline."""

        if self.android_ui_wait_poll_seconds > self.android_ui_wait_timeout_seconds:
            raise ValueError(
                "QA_ANDROID_UI_WAIT_POLL_SECONDS must not exceed "
                "QA_ANDROID_UI_WAIT_TIMEOUT_SECONDS"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one process-wide settings instance."""

    return Settings()
