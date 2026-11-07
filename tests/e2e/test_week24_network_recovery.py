"""Real API faults with bounded removal and business-state recovery."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.data_factories import CatalogApiFactory, item_path
from qa_core.e2e import (
    FaultSpec,
    FaultType,
    RecoveryContext,
    RecoveryJourney,
    RecoveryResult,
)
from qa_core.http import HttpClient, RetryPolicy
from qa_core.resilience import ToxiproxyClient
from qa_core.resilience.toxiproxy import (
    latency_toxic,
    reset_peer_toxic,
    timeout_toxic,
)
from qa_core.resource_pools import NamespaceLease


@dataclass(frozen=True, slots=True)
class ItemFact:
    """One observable server-side catalog fact."""

    item_id: int
    name: str
    status: str


class ProxyItemProbe:
    """Read a catalog item through a reversible proxy without hidden retries."""

    def __init__(
        self,
        *,
        base_url: str,
        workspace_slug: str,
        item_id: int,
        authorization_header: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._path = item_path(item_id, workspace_slug)
        self._item_id = item_id
        self._authorization_header = authorization_header

    def read(self, *, timeout_seconds: float = 1.0) -> ItemFact:
        """Read the item or raise on any non-success transport/server boundary."""

        timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(timeout_seconds, 0.5),
            write=min(timeout_seconds, 0.5),
            pool=min(timeout_seconds, 0.5),
        )
        response = httpx.get(
            f"{self._base_url}{self._path}",
            headers={"Authorization": self._authorization_header},
            timeout=timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"catalog read returned HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("catalog read did not return a JSON object")
        return ItemFact(
            item_id=int(payload["id"]),
            name=str(payload["name"]),
            status=str(payload["status"]),
        )


@contextmanager
def _proxy_item(
    *,
    proxy_url: str,
    namespace: NamespaceLease,
    settings: Settings,
    test_id: str,
) -> Iterator[ProxyItemProbe]:
    http_client = HttpClient(
        base_url=proxy_url,
        timeout=httpx.Timeout(1.0),
        retry_policy=RetryPolicy(
            max_attempts=1,
            backoff_seconds=0.0,
            max_backoff_seconds=0.0,
            jitter_ratio=0.0,
        ),
    )
    with AuthClient.from_settings(
        settings,
        http_client=http_client,
    ) as auth:
        auth.login(namespace.owner_email, settings.auth_test_password)
        tokens = auth.tokens
        assert tokens is not None
        factory = CatalogApiFactory(
            auth=auth,
            workspace_slug=namespace.slug,
            client_id=f"week24-{test_id.lower()}-{uuid4().hex[:8]}",
        )
        try:
            created = factory.create(name=f"Week 24 {test_id}")
            if created.status_code != 201:
                raise RuntimeError(
                    f"catalog setup returned HTTP {created.status_code}"
                )
            item_id = int(created.json()["id"])
            yield ProxyItemProbe(
                base_url=proxy_url,
                workspace_slug=namespace.slug,
                item_id=item_id,
                authorization_header=tokens.authorization_header,
            )
        finally:
            factory.cleanup()


def _observe_failure(probe: ProxyItemProbe) -> dict[str, object]:
    try:
        fact = probe.read(timeout_seconds=0.05)
    except (httpx.HTTPError, RuntimeError) as exc:
        return {"kind": "request_failed", "error_type": type(exc).__name__}
    return {"kind": "unexpected_success", "status": fact.status}


def _run_journey(
    *,
    probe: ProxyItemProbe,
    spec: FaultSpec,
    inject: Callable[[], object],
    remove: Callable[[], object],
    tmp_path: Path,
    test_id: str,
) -> RecoveryResult[ItemFact, dict[str, object]]:
    baseline: ItemFact | None = None

    def read_baseline() -> ItemFact:
        nonlocal baseline
        baseline = probe.read(timeout_seconds=1.0)
        return baseline

    def verify(recovered: ItemFact) -> None:
        assert baseline is not None
        assert recovered == baseline

    def inject_fault() -> None:
        inject()

    def remove_fault() -> None:
        remove()

    return RecoveryJourney[ItemFact, dict[str, object]](
        baseline=read_baseline,
        inject=inject_fault,
        observe=lambda: _observe_failure(probe),
        remove=remove_fault,
        probe=lambda: probe.read(timeout_seconds=1.0),
        is_recovered=lambda fact: fact == baseline,
        verify=verify,
    ).execute(
        RecoveryContext(
            run_id=uuid4().hex[:8],
            worker_id="e2e",
            test_id=test_id,
            scenario_id="RECOVERY-API-BUSINESS-STATE",
            platform="api",
            artifact_dir=tmp_path / "week24" / test_id / "api",
        ),
        spec,
    )


@pytest.mark.e2e
@pytest.mark.api
@pytest.mark.fault_injection
@pytest.mark.timeout(120)
def test_latency_toxic_times_out_and_business_read_recovers(
    e2e_fault_proxy: tuple[ToxiproxyClient, str, str],
    namespace: NamespaceLease,
    settings: Settings,
    sut_api_url: str,
    tmp_path: Path,
) -> None:
    del sut_api_url
    client, proxy_name, proxy_url = e2e_fault_proxy
    test_id = "W24-API-NET-001"
    with _proxy_item(
        proxy_url=proxy_url,
        namespace=namespace,
        settings=settings,
        test_id=test_id,
    ) as probe:
        result = _run_journey(
            probe=probe,
            spec=FaultSpec(
                fault_type=FaultType.NETWORK_LATENCY,
                target=proxy_name,
                expected_boundary="read timeout under the request budget",
                timeout_seconds=5.0,
                parameters=(("latency_ms", 300),),
            ),
            inject=lambda: client.add_toxic(
                proxy_name,
                latency_toxic(latency_ms=300),
            ),
            remove=lambda: client.remove_toxic(proxy_name, "latency"),
            tmp_path=tmp_path,
            test_id=test_id,
        )

    assert result.observed == {
        "kind": "request_failed",
        "error_type": "ReadTimeout",
    }


@pytest.mark.e2e
@pytest.mark.api
@pytest.mark.fault_injection
@pytest.mark.timeout(120)
def test_timeout_toxic_is_removed_and_business_state_returns(
    e2e_fault_proxy: tuple[ToxiproxyClient, str, str],
    namespace: NamespaceLease,
    settings: Settings,
    sut_api_url: str,
    tmp_path: Path,
) -> None:
    del sut_api_url
    client, proxy_name, proxy_url = e2e_fault_proxy
    test_id = "W24-API-NET-002"
    with _proxy_item(
        proxy_url=proxy_url,
        namespace=namespace,
        settings=settings,
        test_id=test_id,
    ) as probe:
        result = _run_journey(
            probe=probe,
            spec=FaultSpec(
                fault_type=FaultType.NETWORK_TIMEOUT,
                target=proxy_name,
                expected_boundary="request cannot complete within the read budget",
                timeout_seconds=5.0,
                parameters=(("timeout_ms", 250),),
            ),
            inject=lambda: client.add_toxic(
                proxy_name,
                timeout_toxic(timeout_ms=250),
            ),
            remove=lambda: client.remove_toxic(proxy_name, "timeout"),
            tmp_path=tmp_path,
            test_id=test_id,
        )

    assert result.observed["kind"] == "request_failed"
    assert result.observed["error_type"] in {
        "ReadTimeout",
        "RemoteProtocolError",
        "RuntimeError",
    }


@pytest.mark.e2e
@pytest.mark.api
@pytest.mark.fault_injection
@pytest.mark.timeout(120)
def test_reset_peer_is_removed_and_a_new_read_recovers(
    e2e_fault_proxy: tuple[ToxiproxyClient, str, str],
    namespace: NamespaceLease,
    settings: Settings,
    sut_api_url: str,
    tmp_path: Path,
) -> None:
    del sut_api_url
    client, proxy_name, proxy_url = e2e_fault_proxy
    test_id = "W24-API-NET-003"
    with _proxy_item(
        proxy_url=proxy_url,
        namespace=namespace,
        settings=settings,
        test_id=test_id,
    ) as probe:
        result = _run_journey(
            probe=probe,
            spec=FaultSpec(
                fault_type=FaultType.NETWORK_RESET,
                target=proxy_name,
                expected_boundary="established connection is reset",
                timeout_seconds=5.0,
            ),
            inject=lambda: client.add_toxic(
                proxy_name,
                reset_peer_toxic(),
            ),
            remove=lambda: client.remove_toxic(proxy_name, "reset-peer"),
            tmp_path=tmp_path,
            test_id=test_id,
        )

    assert result.observed["kind"] == "request_failed"


@pytest.mark.e2e
@pytest.mark.api
@pytest.mark.fault_injection
@pytest.mark.timeout(120)
def test_disabled_proxy_recovers_when_enabled(
    e2e_fault_proxy: tuple[ToxiproxyClient, str, str],
    namespace: NamespaceLease,
    settings: Settings,
    sut_api_url: str,
    tmp_path: Path,
) -> None:
    del sut_api_url
    client, proxy_name, proxy_url = e2e_fault_proxy
    test_id = "W24-API-NET-004"
    with _proxy_item(
        proxy_url=proxy_url,
        namespace=namespace,
        settings=settings,
        test_id=test_id,
    ) as probe:
        result = _run_journey(
            probe=probe,
            spec=FaultSpec(
                fault_type=FaultType.PROXY_DISABLED,
                target=proxy_name,
                expected_boundary="request fails before reaching the API",
                timeout_seconds=5.0,
            ),
            inject=lambda: client.set_proxy_enabled(proxy_name, enabled=False),
            remove=lambda: client.set_proxy_enabled(proxy_name, enabled=True),
            tmp_path=tmp_path,
            test_id=test_id,
        )

    assert result.observed["kind"] == "request_failed"


@pytest.mark.e2e
@pytest.mark.api
@pytest.mark.fault_injection
@pytest.mark.timeout(120)
def test_unavailable_upstream_is_reconfigured_and_business_read_recovers(
    e2e_fault_proxy: tuple[ToxiproxyClient, str, str],
    namespace: NamespaceLease,
    settings: Settings,
    sut_api_url: str,
    tmp_path: Path,
) -> None:
    del sut_api_url
    client, proxy_name, proxy_url = e2e_fault_proxy
    listen = f"0.0.0.0:{urlparse(proxy_url).port}"
    test_id = "W24-API-SVC-001"

    def restore_upstream() -> None:
        client.delete_proxy(proxy_name)
        client.ensure_proxy(
            name=proxy_name,
            listen=listen,
            upstream="api:8000",
        )

    def make_upstream_unavailable() -> None:
        client.delete_proxy(proxy_name)
        client.ensure_proxy(
            name=proxy_name,
            listen=listen,
            upstream="api:8999",
        )

    with _proxy_item(
        proxy_url=proxy_url,
        namespace=namespace,
        settings=settings,
        test_id=test_id,
    ) as probe:
        result = _run_journey(
            probe=probe,
            spec=FaultSpec(
                fault_type=FaultType.SERVICE_UNAVAILABLE,
                target=proxy_name,
                expected_boundary="upstream service unavailable",
                timeout_seconds=5.0,
                parameters=(("upstream", "api:8999"),),
            ),
            inject=make_upstream_unavailable,
            remove=restore_upstream,
            tmp_path=tmp_path,
            test_id=test_id,
        )

    assert result.observed["kind"] == "request_failed"
