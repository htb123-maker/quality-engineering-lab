"""Read-only API smoke tests for the local SUT."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import allure
import httpx
import pytest


@allure.epic("Quality Engineering Lab")
@allure.feature("SUT API")
@allure.story("Read-only catalog smoke")
@pytest.mark.api
@pytest.mark.smoke
@allure.testcase("SMOKE-API-SUT-001", "SUT readiness and seeded catalog")
@allure.link("docs/runbooks/failed-quality-gate.md", name="Failure triage runbook")
def test_sut_readiness_and_seeded_catalog_smoke(sut_api_url: str) -> None:
    with httpx.Client(base_url=sut_api_url, timeout=5.0) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        catalog = client.get("/api/v1/workspaces/atlas/catalog")

    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert catalog.status_code == 200

    payload = catalog.json()
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
