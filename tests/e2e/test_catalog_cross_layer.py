"""API setup, Android UI action, and normal API verification."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import uuid4

import allure
import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory
from qa_core.e2e import E2eContext, E2eJourney, E2eStepFailure, FixtureSessionApi
from qa_core.mobile.platforms import MobilePlatform
from qa_core.platforms.android import AndroidFixtureAdapter
from qa_core.resource_pools import NamespaceLease

from tests.e2e.conftest import role_auth
from tests.e2e.support import (
    CatalogMobilePort,
    CatalogSetupPort,
    CatalogVerificationPort,
    E2eCase,
    catalog_item_response,
    load_cases,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES = load_cases(PROJECT_ROOT / "configs" / "e2e-test-inventory.yaml")


@pytest.fixture(params=CASES, ids=[case.test_id for case in CASES])
def case(request: pytest.FixtureRequest) -> E2eCase:
    return cast(E2eCase, request.param)


@pytest.mark.e2e
@pytest.mark.android
@pytest.mark.timeout(900)
def test_android_api_ui_api_cross_layer_case(
    case: E2eCase,
    android_e2e_adapter: AndroidFixtureAdapter,
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
    owner_auth: AuthClient,
    settings: Settings,
    sut_api_url: str,
    project_root: Path,
) -> None:
    """Execute one non-duplicate Android API + UI + API scenario."""

    allure.dynamic.testcase(case.test_id, case.action)
    context = E2eContext(
        run_id=uuid4().hex[:8],
        worker_id=case.role,
        test_id=case.test_id,
        scenario_id="E2E-CATALOG-CROSS-LAYER",
        platform=MobilePlatform.ANDROID,
        artifact_dir=(
            project_root
            / "artifacts"
            / "e2e"
            / "week23"
            / case.test_id
            / "android"
        ),
    )

    with role_auth(
        role=case.role,
        namespace=namespace,
        owner_auth=owner_auth,
        settings=settings,
    ) as auth:
        fixture_api = FixtureSessionApi(
            auth,
            base_url=sut_api_url,
            client_id=f"week23-{case.test_id.lower()}",
        )
        setup_port = CatalogSetupPort(
            factory=catalog_items,
            fixture_api=fixture_api,
            case=case,
            mobile_base_url=str(settings.android_e2e_api_base_url).rstrip("/"),
            redis_url=str(settings.redis_url),
            settings_client_id=f"week23-{case.test_id.lower()}",
        )
        verification = CatalogVerificationPort(catalog_items)
        journey = E2eJourney(
            setup=setup_port,
            mobile=CatalogMobilePort(android_e2e_adapter, case),
            verification=verification,
        )

        result = None
        setup = setup_port.prepare(context)
        try:
            result = journey.execute(context)
            ui_status = result.ui.status
        except E2eStepFailure:
            ui_status = "error"

        if case.action == "repeat-archive" and ui_status == "archived":
            try:
                android_e2e_adapter.catalog.archive()
            except Exception:  # noqa: BLE001 - expected UI boundary
                ui_status = "error"

        server_response = catalog_item_response(catalog_items, setup.item_id)
        if case.expected_api == "not-found":
            assert server_response.status_code == 404
        else:
            assert server_response.status_code == 200
            assert server_response.json()["status"] == case.expected_api

        assert ui_status == case.expected_ui
        if result is not None:
            assert result.server.status == case.expected_api
            assert result.evidence_path is not None

        if case.request_id_required:
            assert setup.api_request_id
            assert server_response.headers.get("X-QA-Request-Id")

