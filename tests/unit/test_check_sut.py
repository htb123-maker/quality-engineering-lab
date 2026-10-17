"""Week 1 SUT diagnostics must fail clearly when psycopg cannot load."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_check_sut() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_sut.py"
    spec = importlib.util.spec_from_file_location("week1_check_sut", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_missing_psycopg_returns_actionable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_check_sut()
    monkeypatch.setattr(module, "psycopg", None)
    monkeypatch.setattr(
        module,
        "PSYCOPG_IMPORT_ERROR",
        "ImportError: blocked by application control policy",
    )

    results = module.check_postgres("postgresql://qa:qa@127.0.0.1:15432/qa")

    assert len(results) == 1
    assert results[0].name == "PostgreSQL"
    assert results[0].passed is False
    assert "psycopg import failed" in results[0].detail
    assert "Smart App Control" in results[0].detail
