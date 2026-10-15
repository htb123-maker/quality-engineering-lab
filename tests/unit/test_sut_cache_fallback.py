"""A cache outage must degrade the catalog read, not break it."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import app as sut_app
import pytest
import redis
from qa_core.contracts import CatalogItem, CatalogResponse, CatalogWorkspace


def sample_catalog() -> CatalogResponse:
    """Return one catalog response that stands in for a database read."""

    return CatalogResponse(
        workspace=CatalogWorkspace(slug="atlas", name="Atlas Workspace"),
        items=[
            CatalogItem(
                id=1,
                sku="LAB-001",
                name="Lab notebook",
                price_cents=1200,
                status="active",
            )
        ],
        count=1,
    )


def test_catalog_read_uses_postgresql_when_redis_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis is an accelerator here: losing it must fall back to the source."""

    expected = sample_catalog()
    reads: list[str] = []

    def raise_connection_error() -> redis.Redis:
        raise redis.ConnectionError("redis is down")

    def fake_catalog_payload(slug: str) -> tuple[HTTPStatus, CatalogResponse]:
        reads.append(slug)
        return HTTPStatus.OK, expected

    monkeypatch.setattr(sut_app, "_redis_client", raise_connection_error)
    monkeypatch.setattr(sut_app, "_catalog_payload", fake_catalog_payload)

    status, payload, headers = sut_app._catalog_with_cache("atlas")

    assert status == HTTPStatus.OK
    assert payload == expected
    assert headers == {"X-Cache": "BYPASS", "X-Cache-TTL": "-1"}
    assert reads == ["atlas"]


def test_cache_aside_surfaces_redis_errors_to_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper, not the read path, owns the degradation decision."""

    def raise_connection_error() -> Any:
        raise redis.ConnectionError("redis is down")

    monkeypatch.setattr(sut_app, "_redis_client", raise_connection_error)

    with pytest.raises(redis.ConnectionError):
        sut_app._catalog_cache_aside("atlas")
