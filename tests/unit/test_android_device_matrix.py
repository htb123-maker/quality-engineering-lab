"""Unit tests for Android device-matrix loading and worker assignment."""

from pathlib import Path

import pytest
from qa_core.platforms.android.devices import (
    AndroidDeviceProfile,
    load_android_device_matrix,
    select_worker_device,
    xdist_worker_context,
)


def write_matrix(path: Path, devices: str) -> Path:
    path.write_text(f"version: 1\ndevices:\n{devices}", encoding="utf-8")
    return path


@pytest.mark.unit
def test_device_matrix_resolves_environment_and_omits_missing_optional_device(
    tmp_path: Path,
) -> None:
    matrix = write_matrix(
        tmp_path / "matrix.yaml",
        """
  - id: primary
    role: primary
    udid_env: PRIMARY_UDID
    default_udid: emulator-5554
    platform_version: "15"
    required: true
  - id: physical
    role: physical
    udid_env: PHYSICAL_UDID
    default_udid: ""
    platform_version: ""
    required: false
""",
    )

    profiles = load_android_device_matrix(
        matrix,
        {"PRIMARY_UDID": "device-primary"},
    )

    assert profiles == (
        AndroidDeviceProfile(
            device_id="primary",
            role="primary",
            udid="device-primary",
            platform_version="15",
            required=True,
        ),
    )


@pytest.mark.unit
def test_device_matrix_can_select_physical_device_with_version_override(
    tmp_path: Path,
) -> None:
    matrix = write_matrix(
        tmp_path / "matrix.yaml",
        """
  - id: primary
    role: primary
    udid_env: PRIMARY_UDID
    default_udid: emulator-5554
    platform_version: "15"
    required: true
  - id: physical
    role: physical
    udid_env: PHYSICAL_UDID
    platform_version: ""
    platform_version_env: PHYSICAL_VERSION
    required: false
""",
    )

    profiles = load_android_device_matrix(
        matrix,
        {
            "QA_ANDROID_DEVICE_IDS": "physical",
            "PHYSICAL_UDID": "physical-serial",
            "PHYSICAL_VERSION": "14",
        },
    )

    assert profiles == (
        AndroidDeviceProfile(
            device_id="physical",
            role="physical",
            udid="physical-serial",
            platform_version="14",
            required=False,
        ),
    )


@pytest.mark.unit
def test_device_matrix_rejects_selected_device_without_udid(
    tmp_path: Path,
) -> None:
    matrix = write_matrix(
        tmp_path / "matrix.yaml",
        """
  - id: primary
    role: primary
    udid_env: PRIMARY_UDID
    default_udid: emulator-5554
    platform_version: "15"
    required: true
  - id: physical
    role: physical
    udid_env: PHYSICAL_UDID
    platform_version: ""
    required: false
""",
    )

    with pytest.raises(ValueError, match="selected Android device 'physical' has no UDID"):
        load_android_device_matrix(
            matrix,
            {"QA_ANDROID_DEVICE_IDS": "physical"},
        )


@pytest.mark.unit
def test_device_matrix_rejects_unknown_selected_device(tmp_path: Path) -> None:
    matrix = write_matrix(
        tmp_path / "matrix.yaml",
        """
  - id: primary
    role: primary
    udid_env: PRIMARY_UDID
    default_udid: emulator-5554
    platform_version: "15"
    required: true
""",
    )

    with pytest.raises(ValueError, match="unknown device id"):
        load_android_device_matrix(
            matrix,
            {"QA_ANDROID_DEVICE_IDS": "missing"},
        )


@pytest.mark.unit
def test_device_matrix_rejects_duplicate_udids(tmp_path: Path) -> None:
    matrix = write_matrix(
        tmp_path / "matrix.yaml",
        """
  - id: first
    role: primary
    udid_env: FIRST
    default_udid: emulator-5554
    platform_version: "15"
    required: true
  - id: second
    role: parallel
    udid_env: SECOND
    default_udid: emulator-5554
    platform_version: "15"
    required: false
""",
    )

    with pytest.raises(ValueError, match="duplicate UDIDs"):
        load_android_device_matrix(matrix, {})


@pytest.mark.unit
def test_worker_selection_requires_a_distinct_configured_device() -> None:
    profiles = (
        AndroidDeviceProfile("primary", "primary", "emulator-5554", "15", True),
        AndroidDeviceProfile("parallel", "parallel", "emulator-5556", "15", True),
    )

    assert select_worker_device(profiles, "gw0", 2).device_id == "primary"
    assert select_worker_device(profiles, "gw1", 2).device_id == "parallel"

    with pytest.raises(ValueError, match="matrix has 2 active"):
        select_worker_device(profiles, "gw2", 3)


@pytest.mark.unit
def test_xdist_context_parses_worker_index_and_count() -> None:
    assert xdist_worker_context({}) == (0, 1)
    assert (
        xdist_worker_context(
            {
                "PYTEST_XDIST_WORKER": "gw1",
                "PYTEST_XDIST_WORKER_COUNT": "2",
            }
        )
        == (1, 2)
    )

    with pytest.raises(ValueError, match="outside"):
        xdist_worker_context(
            {
                "PYTEST_XDIST_WORKER": "gw2",
                "PYTEST_XDIST_WORKER_COUNT": "2",
            }
        )
