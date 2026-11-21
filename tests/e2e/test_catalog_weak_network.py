"""Real SUT catalog behavior through an Android weak-network proxy."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from uuid import uuid4

import allure
import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory
from qa_core.e2e import E2eContext, FixtureSessionApi
from qa_core.mobile.platforms import MobilePlatform
from qa_core.platforms.android import AndroidFixtureAdapter
from qa_core.resilience import ToxiproxyClient
from qa_core.resilience.toxiproxy import latency_toxic, timeout_toxic
from qa_core.resource_pools import NamespaceLease

from tests.e2e.support import (
    CatalogSetupPort,
    CatalogVerificationPort,
    E2eCase,
    catalog_item_response,
)


def _case() -> E2eCase:
    return E2eCase(
        test_id="W32-AND-WEAK-NETWORK",
        role="owner",
        item_state="active",
        session_state="valid",
        action="read",
        expected_ui="active",
        expected_api="active",
        request_id_required=True,
    )


def _run_adb(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["adb", *args],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


@pytest.mark.e2e
@pytest.mark.android
@pytest.mark.fault_injection
@pytest.mark.recovery
@pytest.mark.timeout(300)
def test_real_sut_catalog_recovers_after_latency_and_packet_timeout(
    android_e2e_adapter: AndroidFixtureAdapter,
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
    owner_auth: AuthClient,
    settings: Settings,
    sut_api_url: str,
    project_root: Path,
    toxiproxy: ToxiproxyClient,
) -> None:
    """Delay and drop the real catalog API, then verify recovery and state."""

    proxy_port = settings.toxiproxy_proxy_port_base
    proxy_name = f"week32-android-weak-{uuid4().hex[:8]}"
    proxy = toxiproxy.ensure_proxy(
        name=proxy_name,
        listen=f"0.0.0.0:{proxy_port}",
        upstream="api:8000",
    )
    reverse = _run_adb(
        "-s",
        settings.android_udid,
        "reverse",
        f"tcp:{proxy_port}",
        f"tcp:{proxy_port}",
    )
    assert reverse.returncode == 0, reverse.stderr

    context = E2eContext(
        run_id=uuid4().hex[:8],
        worker_id="week32",
        test_id="W32-AND-WEAK-NETWORK",
        scenario_id="W32-AND-WEAK-NETWORK",
        platform=MobilePlatform.ANDROID,
        artifact_dir=project_root / "artifacts" / "e2e" / "week32" / "android-weak",
    )
    mobile_base_url = f"http://127.0.0.1:{proxy_port}"
    setup_port = CatalogSetupPort(
        factory=catalog_items,
        fixture_api=FixtureSessionApi(
            owner_auth,
            base_url=sut_api_url,
            client_id="week32-android-weak",
        ),
        case=_case(),
        mobile_base_url=mobile_base_url,
        redis_url=str(settings.redis_url),
        settings_client_id="week32-android-weak",
    )

    try:
        setup = setup_port.prepare(context)
        baseline = android_e2e_adapter.catalog.open(
            base_url=mobile_base_url,
            session_id=setup.fixture_session_id,
        )
        assert baseline.status == "active"

        toxiproxy.add_toxic(
            proxy.name,
            latency_toxic(latency_ms=1_500, name="week32-latency"),
        )
        started = time.perf_counter()
        delayed = android_e2e_adapter.catalog.open(
            base_url=mobile_base_url,
            session_id=setup.fixture_session_id,
        )
        delay_seconds = time.perf_counter() - started
        assert delayed.status == "active"
        assert delay_seconds >= 1.0
        toxiproxy.remove_toxic(proxy.name, "week32-latency")

        toxiproxy.add_toxic(
            proxy.name,
            timeout_toxic(timeout_ms=7_000, name="week32-timeout"),
        )
        dropped = android_e2e_adapter.catalog.open(
            base_url=mobile_base_url,
            session_id=setup.fixture_session_id,
        )
        assert dropped.status == "error"
        toxiproxy.remove_toxic(proxy.name, "week32-timeout")

        recovered = android_e2e_adapter.catalog.open(
            base_url=mobile_base_url,
            session_id=setup.fixture_session_id,
        )
        assert recovered.status == "active"
        assert recovered.item_id == setup.item_id
        assert recovered.name == setup.item_name

        archived = android_e2e_adapter.catalog.archive()
        server = CatalogVerificationPort(catalog_items).verify(setup)
        response = catalog_item_response(catalog_items, setup.item_id)
        assert archived.status == "archived"
        assert server.status == "archived"
        assert response.status_code == 200
        assert response.json()["status"] == "archived"

        allure.attach(
            (
                f"baseline=active\n"
                f"latency_ms=1500\n"
                f"observed_delay_seconds={delay_seconds:.3f}\n"
                f"timeout_ms=7000\n"
                f"dropped={dropped.status}\n"
                f"recovered={recovered.status}\n"
                f"archived={archived.status}\n"
                f"server={server.status}"
            ),
            name="weak-network-business-evidence",
            attachment_type=allure.attachment_type.TEXT,
        )
    finally:
        toxiproxy.delete_proxy(proxy.name)
        _run_adb(
            "-s",
            settings.android_udid,
            "reverse",
            "--remove",
            f"tcp:{proxy_port}",
        )
