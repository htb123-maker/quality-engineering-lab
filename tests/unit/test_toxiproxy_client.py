"""Control-plane tests for the Toxiproxy helper."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from qa_core.resilience import Toxic, ToxiproxyClient
from qa_core.resilience.toxiproxy import latency_toxic, reset_peer_toxic

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.mark.unit
def test_proxy_lifecycle_uses_documented_control_api() -> None:
    proxies: dict[str, dict[str, object]] = {}
    toxics: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/proxies":
            return httpx.Response(200, json=proxies)
        if request.method == "POST" and path == "/proxies":
            payload = json.loads(request.content)
            proxy = {**payload, "enabled": True}
            proxies[str(payload["name"])] = proxy
            return httpx.Response(201, json=proxy)
        if request.method == "DELETE" and path.startswith("/proxies/"):
            proxies.pop(path.rsplit("/", 1)[-1], None)
            return httpx.Response(204)
        if request.method == "PATCH" and path.startswith("/proxies/"):
            name = path.rsplit("/", 1)[-1]
            payload = json.loads(request.content)
            proxies[name]["enabled"] = payload["enabled"]
            return httpx.Response(200, json=proxies[name])
        if request.method == "POST" and path.endswith("/toxics"):
            payload = json.loads(request.content)
            toxics.append(payload)
            return httpx.Response(200, json=payload)
        raise AssertionError(f"unexpected request: {request.method} {path}")

    with ToxiproxyClient(
        "http://control.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        created = client.ensure_proxy(
            name="sut-api-gw0",
            listen="0.0.0.0:18100",
            upstream="api:8000",
        )
        again = client.ensure_proxy(
            name="sut-api-gw0",
            listen="0.0.0.0:18100",
            upstream="api:8000",
        )
        disabled = client.set_proxy_enabled("sut-api-gw0", enabled=False)
        client.add_toxic(
            "sut-api-gw0",
            latency_toxic(latency_ms=250, jitter_ms=10),
        )

    assert created.enabled is True
    assert again == created
    assert disabled.enabled is False
    assert toxics == [
        {
            "name": "latency",
            "type": "latency",
            "stream": "downstream",
            "toxicity": 1.0,
            "attributes": {"latency": 250, "jitter": 10},
        }
    ]


@pytest.mark.unit
def test_reset_peer_toxic_is_explicit_and_serializable() -> None:
    toxic = reset_peer_toxic()

    assert isinstance(toxic, Toxic)
    assert toxic.type == "reset_peer"
    assert toxic.toxicity == 1.0
