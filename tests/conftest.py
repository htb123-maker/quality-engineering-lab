"""Shared pytest fixtures."""

from pathlib import Path

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
