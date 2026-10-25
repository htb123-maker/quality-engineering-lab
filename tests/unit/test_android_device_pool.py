"""Unit tests for cross-host Android Appium pool configuration."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_device_pool() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "verify_android_device_pool.py"
    )
    spec = importlib.util.spec_from_file_location(
        "week16_android_device_pool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_pool(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.unit
def test_pool_allows_same_serial_on_different_hosts(tmp_path: Path) -> None:
    module = _load_device_pool()
    config = write_pool(
        tmp_path / "pool.yaml",
        """
endpoints:
  - name: local
    appium_url: http://127.0.0.1:4723
    serial: emulator-5554
    system_port: 8200
    mjpeg_server_port: 7810
  - name: remote
    appium_url: http://192.0.2.10:4723
    serial: emulator-5554
    system_port: 8201
    mjpeg_server_port: 7811
""",
    )

    endpoints = module.load_pool(config)

    assert len(endpoints) == 2
    assert endpoints[0].serial == endpoints[1].serial
    assert endpoints[0].appium_url != endpoints[1].appium_url


@pytest.mark.unit
def test_pool_rejects_duplicate_target(tmp_path: Path) -> None:
    module = _load_device_pool()
    config = write_pool(
        tmp_path / "pool.yaml",
        """
endpoints:
  - name: first
    appium_url: http://127.0.0.1:4723
    serial: emulator-5554
    system_port: 8200
    mjpeg_server_port: 7810
  - name: duplicate
    appium_url: http://127.0.0.1:4723/
    serial: emulator-5554
    system_port: 8201
    mjpeg_server_port: 7811
""",
    )

    with pytest.raises(ValueError, match="duplicate endpoint target"):
        module.load_pool(config)


@pytest.mark.unit
def test_pool_rejects_invalid_port(tmp_path: Path) -> None:
    module = _load_device_pool()
    config = write_pool(
        tmp_path / "pool.yaml",
        """
endpoints:
  - name: local
    appium_url: http://127.0.0.1:4723
    serial: emulator-5554
    system_port: 80
    mjpeg_server_port: 7810
""",
    )

    with pytest.raises(ValueError, match="system_port"):
        module.load_pool(config)
