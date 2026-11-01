"""Shared iOS device-matrix fixtures."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import allure
import pytest
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver
from qa_core.platforms.ios import IosDiagnostics
from qa_core.platforms.ios.devices import (
    IosDeviceMatrix,
    IosDeviceProfile,
    IosWorkerResources,
    allocate_ios_worker_resources,
    build_ios_worker_settings,
    ios_xdist_worker_context,
    load_ios_device_matrix,
)

from tests.ios.fixture import ios_runtime_is_configured


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


@pytest.fixture
def ios_runtime_driver(
    request: pytest.FixtureRequest,
    project_root: Path,
) -> Iterator[Any]:
    """Create one isolated iOS session and capture sanitized failure evidence."""

    if not ios_runtime_is_configured():
        pytest.skip("iOS runtime requires macOS or a configured cloud provider")

    settings = cast(
        Settings,
        request.getfixturevalue("ios_worker_settings"),
    )
    driver = create_ios_driver(settings)
    test_name = request.node.name
    diagnostics = IosDiagnostics(
        driver,
        project_root
        / "artifacts"
        / "ios-week21"
        / settings.ios_run_id
        / "failures"
        / test_name,
    )
    context = {
        "provider": settings.ios_device_provider,
        "device_name": settings.ios_device_name,
        "platform_version": settings.ios_platform_version,
        "bundle_id": settings.ios_bundle_id,
        "appium_server_url": str(settings.appium_server_url),
        "run_id": settings.ios_run_id,
    }
    try:
        yield driver
    except Exception as exc:
        try:
            failure = diagnostics.capture_failure(
                f"{test_name}-failure",
                test_id=test_name,
                error=exc,
                context=context,
            )
            allure.attach.file(
                str(failure.manifest_path),
                name="iOS failure manifest",
                attachment_type=allure.attachment_type.JSON,
            )
        except Exception:
            pass
        raise
    finally:
        driver.quit()
