"""Shared iOS device-matrix fixtures."""

from pathlib import Path

import pytest
from qa_core.config.settings import Settings
from qa_core.platforms.ios.devices import (
    IosDeviceMatrix,
    IosDeviceProfile,
    IosWorkerResources,
    allocate_ios_worker_resources,
    build_ios_worker_settings,
    ios_xdist_worker_context,
    load_ios_device_matrix,
)


@pytest.fixture(scope="session")
def ios_device_matrix(settings: Settings, project_root: Path) -> IosDeviceMatrix:
    """Load the active iOS matrix for this test process."""

    matrix_path = settings.ios_device_matrix
    if not matrix_path.is_absolute():
        matrix_path = project_root / matrix_path
    return load_ios_device_matrix(matrix_path)


@pytest.fixture(scope="session")
def ios_worker_resources(
    ios_device_matrix: IosDeviceMatrix,
    project_root: Path,
) -> IosWorkerResources:
    """Reserve one device and its isolated ports/directories."""

    worker_id, _, worker_count = ios_xdist_worker_context()
    return allocate_ios_worker_resources(
        ios_device_matrix,
        worker_id,
        worker_count,
        project_root,
    )


@pytest.fixture(scope="session")
def ios_worker_profile(ios_worker_resources: IosWorkerResources) -> IosDeviceProfile:
    """Return the device assigned to the current worker."""

    return ios_worker_resources.profile


@pytest.fixture(scope="session")
def ios_worker_settings(
    settings: Settings,
    ios_worker_profile: IosDeviceProfile,
    ios_worker_resources: IosWorkerResources,
) -> Settings:
    """Return Settings targeting only the current worker's iOS profile."""

    return build_ios_worker_settings(
        settings,
        ios_worker_profile,
        ios_worker_resources,
    )
