"""Unit tests for iOS device-matrix resource isolation."""

from pathlib import Path

import pytest
from qa_core.config.settings import Settings
from qa_core.platforms.ios.devices import (
    IosDeviceMatrix,
    IosDeviceProfile,
    allocate_ios_worker_resources,
    build_ios_worker_settings,
    ios_xdist_worker_context,
    load_ios_device_matrix,
    select_ios_worker_device,
)


def write_matrix(path: Path, devices: str) -> Path:
    path.write_text(
        "version: 1\n"
        "appium_port_base: 4723\n"
        "wda_port_base: 8100\n"
        "derived_data_root: artifacts/ios-derived\n"
        f"devices:\n{devices}",
        encoding="utf-8",
    )
    return path


@pytest.mark.unit
def test_matrix_resolves_two_simulators_and_omits_missing_optional(
    tmp_path: Path,
) -> None:
    matrix_path = write_matrix(
        tmp_path / "matrix.yaml",
        """
  - id: current
    role: primary
    provider: local
    capability_profile: simulator
    device_name_env: CURRENT_DEVICE
    platform_version_env: CURRENT_VERSION
    udid_env: CURRENT_UDID
    required: true
  - id: previous
    role: compatibility
    provider: local
    capability_profile: simulator
    device_name_env: PREVIOUS_DEVICE
    platform_version_env: PREVIOUS_VERSION
    udid_env: PREVIOUS_UDID
    required: false
""",
    )

    matrix = load_ios_device_matrix(
        matrix_path,
        {
            "CURRENT_DEVICE": "iPhone 18",
            "CURRENT_VERSION": "18.5",
            "CURRENT_UDID": "udid-current",
        },
    )

    assert matrix.profiles == (
        IosDeviceProfile(
            device_id="current",
            role="primary",
            provider="local",
            capability_profile="simulator",
            device_name="iPhone 18",
            platform_version="18.5",
            udid="udid-current",
            required=True,
        ),
    )
    assert matrix.wda_port_base == 8100
    assert matrix.appium_port_base == 4723
    assert matrix.derived_data_root == Path("artifacts/ios-derived")


@pytest.mark.unit
def test_cloud_profile_does_not_require_udid(tmp_path: Path) -> None:
    matrix_path = write_matrix(
        tmp_path / "matrix.yaml",
        """
  - id: cloud
    role: cloud
    provider: browserstack
    capability_profile: device
    device_name_env: CLOUD_DEVICE
    default_device_name: iPhone 15
    platform_version_env: CLOUD_VERSION
    default_platform_version: "17"
    required: false
""",
    )

    matrix = load_ios_device_matrix(
        matrix_path,
        {"QA_IOS_DEVICE_IDS": "cloud"},
    )

    assert matrix.profiles[0].udid is None
    assert matrix.profiles[0].device_name == "iPhone 15"
    assert matrix.profiles[0].platform_version == "17"


@pytest.mark.unit
def test_selected_local_profile_requires_udid(tmp_path: Path) -> None:
    matrix_path = write_matrix(
        tmp_path / "matrix.yaml",
        """
  - id: current
    role: primary
    provider: local
    capability_profile: simulator
    device_name_env: CURRENT_DEVICE
    device_name_default: ignored
    platform_version_env: CURRENT_VERSION
    required: true
""",
    )

    with pytest.raises(ValueError, match="CURRENT_DEVICE"):
        load_ios_device_matrix(matrix_path, {})


@pytest.mark.unit
def test_matrix_rejects_duplicate_ids_and_udids(tmp_path: Path) -> None:
    duplicate_id = write_matrix(
        tmp_path / "duplicate-id.yaml",
        """
  - id: same
    role: primary
    provider: local
    capability_profile: simulator
    device_name_env: DEVICE
    default_device_name: iPhone 16
    platform_version_env: VERSION
    default_platform_version: "18.5"
    udid_env: FIRST
    default_udid: first
    required: true
  - id: same
    role: second
    provider: local
    capability_profile: simulator
    device_name_env: DEVICE
    default_device_name: iPhone 16
    platform_version_env: VERSION
    default_platform_version: "18.5"
    udid_env: SECOND
    default_udid: second
    required: false
""",
    )
    with pytest.raises(ValueError, match="duplicate iOS device id"):
        load_ios_device_matrix(duplicate_id, {})

    duplicate_udid = write_matrix(
        tmp_path / "duplicate-udid.yaml",
        """
  - id: first
    role: primary
    provider: local
    capability_profile: simulator
    device_name_env: DEVICE
    default_device_name: iPhone 16
    platform_version_env: VERSION
    default_platform_version: "18.5"
    udid_env: FIRST
    default_udid: same
    required: true
  - id: second
    role: parallel
    provider: local
    capability_profile: simulator
    device_name_env: DEVICE
    default_device_name: iPhone 16
    platform_version_env: VERSION
    default_platform_version: "18.5"
    udid_env: SECOND
    default_udid: same
    required: false
""",
    )
    with pytest.raises(ValueError, match="duplicate UDIDs"):
        load_ios_device_matrix(duplicate_udid, {})


@pytest.mark.unit
def test_worker_resources_allocate_unique_ports_and_directories(
    tmp_path: Path,
) -> None:
    matrix_path = write_matrix(
        tmp_path / "matrix.yaml",
        """
  - id: first
    role: primary
    provider: local
    capability_profile: simulator
    device_name_env: FIRST_DEVICE
    default_device_name: iPhone 16
    platform_version_env: FIRST_VERSION
    default_platform_version: "18.5"
    udid_env: FIRST_UDID
    default_udid: first
    required: true
  - id: second
    role: parallel
    provider: local
    capability_profile: simulator
    device_name_env: SECOND_DEVICE
    default_device_name: iPhone 16
    platform_version_env: SECOND_VERSION
    default_platform_version: "18.5"
    udid_env: SECOND_UDID
    default_udid: second
    required: false
""",
    )
    matrix = load_ios_device_matrix(matrix_path, {})

    first = allocate_ios_worker_resources(
        matrix,
        "gw0",
        2,
        tmp_path,
        {"QA_IOS_RUN_ID": "run-42"},
    )
    second = allocate_ios_worker_resources(
        matrix,
        "gw1",
        2,
        tmp_path,
        {"QA_IOS_RUN_ID": "run-42"},
    )

    assert first.profile.device_id == "first"
    assert second.profile.device_id == "second"
    assert (first.wda_local_port, second.wda_local_port) == (8100, 8101)
    assert (first.appium_server_port, second.appium_server_port) == (4723, 4724)
    assert first.derived_data_path != second.derived_data_path
    assert first.derived_data_path == (
        tmp_path / "artifacts" / "ios-derived" / "run-42" / "first"
    ).resolve()


@pytest.mark.unit
def test_worker_selection_rejects_more_workers_than_profiles() -> None:
    profiles = (
        IosDeviceProfile(
            "first",
            "primary",
            "local",
            "simulator",
            "iPhone 16",
            "18.5",
            "first",
            True,
        ),
    )

    with pytest.raises(ValueError, match="matrix has 1 active"):
        select_ios_worker_device(profiles, "gw1", 2)


@pytest.mark.unit
def test_worker_settings_map_profile_and_derived_data_path(tmp_path: Path) -> None:
    profile = IosDeviceProfile(
        "first",
        "primary",
        "local",
        "simulator",
        "iPhone 16",
        "18.5",
        "first",
        True,
    )
    resources = allocate_ios_worker_resources(
        IosDeviceMatrix(
            profiles=(profile,),
            appium_port_base=4723,
            wda_port_base=8100,
            derived_data_root=Path("artifacts/ios-derived"),
        ),
        "gw0",
        1,
        tmp_path,
        {"QA_IOS_RUN_ID": "run-1"},
    )

    settings = build_ios_worker_settings(Settings(_env_file=None), profile, resources)

    assert settings.ios_udid == "first"
    assert settings.ios_device_name == "iPhone 16"
    assert settings.ios_platform_version == "18.5"
    assert settings.ios_wda_local_port == 8100
    assert str(settings.appium_server_url).rstrip("/") == "http://127.0.0.1:4723"
    assert settings.ios_derived_data_path == resources.derived_data_path


@pytest.mark.unit
def test_xdist_context_and_unsafe_run_id_are_rejected() -> None:
    assert ios_xdist_worker_context({}) == ("gw0", 0, 1)
    assert ios_xdist_worker_context(
        {
            "PYTEST_XDIST_WORKER": "gw1",
            "PYTEST_XDIST_WORKER_COUNT": "2",
        }
    ) == ("gw1", 1, 2)

    profile = IosDeviceProfile(
        "first",
        "primary",
        "local",
        "simulator",
        "iPhone 16",
        "18.5",
        "first",
        True,
    )
    matrix = IosDeviceMatrix(
        profiles=(profile,),
        appium_port_base=4723,
        wda_port_base=8100,
        derived_data_root=Path("artifacts/ios-derived"),
    )
    with pytest.raises(ValueError, match="run id"):
        allocate_ios_worker_resources(
            matrix,
            "gw0",
            1,
            Path("."),
            {"QA_IOS_RUN_ID": "../escape"},
        )


@pytest.mark.unit
def test_repository_matrix_declares_required_roles() -> None:
    project_root = Path(__file__).resolve().parents[2]
    matrix = load_ios_device_matrix(
        project_root / "configs" / "ios-device-matrix.yaml",
        {
            "QA_IOS_DEVICE_IDS": "simulator-current-primary",
            "QA_IOS_SIM_CURRENT_DEVICE": "iPhone 16",
            "QA_IOS_SIM_CURRENT_VERSION": "18.5",
            "QA_IOS_SIM_CURRENT_UDID": "current",
        },
    )

    assert [profile.device_id for profile in matrix.profiles] == [
        "simulator-current-primary"
    ]
