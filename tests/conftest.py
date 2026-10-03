"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from qa_core.config.settings import Settings, get_settings


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the repository root independently of the current working directory."""

    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Return immutable process-wide test settings."""

    return get_settings()


@pytest.fixture(scope="session")
def sut_api_url(settings: Settings) -> Iterator[str]:
    """Return the SUT base URL or skip when the local Compose stack is not running."""

    api_base_url = str(settings.api_base_url).rstrip("/")
    try:
        response = httpx.get(f"{api_base_url}/health/live", timeout=1.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"Docker Compose SUT is not running: {type(exc).__name__}: {exc}")

    if response.status_code != 200:
        pytest.fail(f"SUT live endpoint returned HTTP {response.status_code}")

    yield api_base_url
