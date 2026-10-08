"""Read-only API smoke tests for the local SUT."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import json

import allure
import httpx
import pytest
from qa_core.config.settings import Settings
from qa_core.http import HttpClient


def _attach_response(response: httpx.Response, *, name: str) -> None:
    try:
        body: object = response.json()
    except json.JSONDecodeError:
        body = response.text

    payload = {
        "request": {
            "method": response.request.method,
            "path": response.request.url.path,
        },
        "status_code": response.status_code,
        "body": body,
    }
    allure.attach(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("SUT API")
@allure.story("Read-only catalog smoke")
@pytest.mark.api
@pytest.mark.smoke
@allure.testcase("SMOKE-API-SUT-001", "SUT readiness and seeded catalog")
@allure.link("docs/runbooks/failed-quality-gate.md", name="Failure triage runbook")
def test_sut_readiness_and_seeded_catalog_smoke(
    sut_api_url: str,
    settings: Settings,
) -> None:
    with HttpClient.from_settings(settings) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        catalog = client.get("/api/v1/workspaces/atlas/catalog")

    assert str(settings.api_base_url).rstrip("/") == sut_api_url
    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert catalog.status_code == 200
    _attach_response(live, name="Live response")
    _attach_response(ready, name="Ready response")
    _attach_response(catalog, name="Catalog response")

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
