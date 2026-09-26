"""Shared pytest fixtures."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the repository root independently of the current working directory."""

    return Path(__file__).resolve().parents[1]
