"""API-backed iOS catalog smoke using the same shared journey."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory
from qa_core.e2e import E2eContext, E2eJourney, FixtureSessionApi
from qa_core.mobile.platforms import MobilePlatform
from qa_core.platforms.ios import IosFixtureAdapter

from tests.e2e.support import (
    CatalogMobilePort,
    CatalogSetupPort,
    CatalogVerificationPort,
    E2eCase,
)


@pytest.mark.e2e
@pytest.mark.ios
@pytest.mark.timeout(1200)
def test_ios_api_ui_api_catalog_archive_smoke(
    ios_e2e_adapter: IosFixtureAdapter,
    catalog_items: CatalogApiFactory,
    owner_auth: AuthClient,
    settings: Settings,
    sut_api_url: str,
    project_root: Path,
) -> None:
    """Prove the same API-backed catalog journey on an iOS Simulator."""

    case = E2eCase(
        test_id="E2E-IOS-CAT-001",
        role="owner",
        item_state="active",
        session_state="valid",
        action="archive",
        expected_ui="archived",
        expected_api="archived",
        request_id_required=True,
    )
    context = E2eContext(
        run_id=uuid4().hex[:8],
        worker_id="ios",
        test_id=case.test_id,
        scenario_id="E2E-CATALOG-CROSS-LAYER",
        platform=MobilePlatform.IOS,
        artifact_dir=(
            project_root
            / "artifacts"
            / "e2e"
            / "week23"
            / case.test_id
            / "ios"
        ),
    )
    fixture_api = FixtureSessionApi(
        owner_auth,
        base_url=sut_api_url,
        client_id="week23-ios-smoke",
    )
    setup_port = CatalogSetupPort(
        factory=catalog_items,
        fixture_api=fixture_api,
        case=case,
        mobile_base_url=str(settings.ios_e2e_api_base_url).rstrip("/"),
        redis_url=str(settings.redis_url),
        settings_client_id="week23-ios-smoke",
    )
    result = E2eJourney(
        setup=setup_port,
        mobile=CatalogMobilePort(ios_e2e_adapter, case),
        verification=CatalogVerificationPort(catalog_items),
    ).execute(context)

    assert result.ui.status == "archived"
    assert result.server.status == "archived"
    assert result.setup.api_request_id
    assert result.server.request_id
    assert result.evidence_path is not None
