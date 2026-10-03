"""Read-only integration tests for the Docker Compose SUT."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import allure
import httpx
import psycopg
import pytest
import redis
from psycopg.rows import dict_row
from qa_core.config.settings import Settings


@allure.epic("Quality Engineering Lab")
@allure.feature("Local SUT")
@allure.story("Health checks")
@pytest.mark.integration
def test_sut_is_live_and_ready(sut_api_url: str) -> None:
    with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert ready.status_code == 200

    payload = ready.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["postgres"]["status"] == "ok"
    assert payload["checks"]["redis"]["status"] == "ok"


@allure.epic("Quality Engineering Lab")
@allure.feature("Local SUT")
@allure.story("Seed data")
@pytest.mark.integration
def test_catalog_endpoint_returns_seeded_read_only_data(sut_api_url: str) -> None:
    with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
        response = client.get("/api/v1/workspaces/atlas/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace"] == {
        "slug": "atlas",
        "name": "Atlas Workspace",
    }
    assert payload["count"] == 3
    assert [item["sku"] for item in payload["items"]] == [
        "LAB-001",
        "LAB-002",
        "LAB-003",
    ]


@allure.epic("Quality Engineering Lab")
@allure.feature("Local SUT")
@allure.story("PostgreSQL schema and seed")
@pytest.mark.integration
def test_postgres_schema_seed_and_view_are_queryable_read_only(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with psycopg.connect(str(settings.postgres_dsn), connect_timeout=5) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT slug, item_count, catalog_value_cents
                FROM workspace_catalog_summary
                ORDER BY workspace_id
                """
            )
            rows = cursor.fetchall()

    assert rows == [
        {
            "slug": "atlas",
            "item_count": 2,
            "catalog_value_cents": 5898,
        },
        {
            "slug": "orbit",
            "item_count": 1,
            "catalog_value_cents": 7999,
        },
    ]


@allure.epic("Quality Engineering Lab")
@allure.feature("Local SUT")
@allure.story("Redis connectivity")
@pytest.mark.integration
def test_redis_is_reachable(sut_api_url: str, settings: Settings) -> None:
    del sut_api_url

    client = redis.Redis.from_url(
        str(settings.redis_url),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        assert client.ping() is True
        assert client.dbsize() >= 0
    finally:
        client.close()
