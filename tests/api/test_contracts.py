"""Live OpenAPI and response-model contract tests for the local SUT."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import json
from typing import Any

import allure
import pytest
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.contracts import (
    AdminAuditResponse,
    ApiError,
    CatalogResponse,
    OidcMetadataResponse,
    TokenResponse,
    UserResponse,
    openapi_document,
    validate_contract,
)
from qa_core.http import HttpClient


def _attach_contract(name: str, payload: object) -> None:
    allure.attach(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("API Contract")
@allure.story("OpenAPI and runtime response models")
@pytest.mark.api
@allure.testcase("API-CONTRACT-001", "OpenAPI matches runtime responses")
def test_openapi_document_and_runtime_responses_share_contracts(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        openapi_response = client.get("/openapi.json")
        discovery_response = client.get("/.well-known/openid-configuration")
        token_response = client.post(
            settings.auth_token_path,
            data={
                "grant_type": "password",
                "username": settings.auth_test_username,
                "password": settings.auth_test_password,
                "scope": "openid profile",
            },
        )
        catalog_response = client.get("/api/v1/workspaces/atlas/catalog")

    assert openapi_response.status_code == 200
    assert openapi_response.json() == openapi_document()
    validate_contract(OidcMetadataResponse, discovery_response.json())
    token = validate_contract(TokenResponse, token_response.json())
    catalog = validate_contract(CatalogResponse, catalog_response.json())

    with AuthClient.from_settings(settings) as auth:
        auth.login(
            settings.auth_test_username,
            settings.auth_test_password,
        )
        me_response = auth.get("/api/v1/auth/me")
        audit_response = auth.get("/api/v1/admin/audit")

    me = validate_contract(UserResponse, me_response.json())
    audit = validate_contract(AdminAuditResponse, audit_response.json())

    assert token.expires_in > 0
    assert catalog.count == len(catalog.items)
    assert me.email == settings.auth_test_username
    assert audit.role == "owner"
    _attach_contract(
        "OpenAPI contract summary",
        {
            "openapi": openapi_response.json()["openapi"],
            "paths": sorted(openapi_response.json()["paths"]),
            "components": sorted(
                openapi_response.json()["components"]["schemas"]
            ),
        },
    )
    _attach_contract(
        "Validated runtime contracts",
        {
            "catalog": catalog.model_dump(mode="json"),
            "user": me.model_dump(mode="json"),
            "audit": audit.model_dump(mode="json"),
        },
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("API Contract")
@allure.story("Structured error response")
@pytest.mark.api
@allure.testcase("API-CONTRACT-002", "403 response matches the error model")
def test_runtime_error_response_matches_shared_error_contract(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with AuthClient.from_settings(settings) as client:
        client.login(
            "viewer@atlas.example",
            settings.auth_test_password,
        )
        response = client.get("/api/v1/admin/audit")

    error = validate_contract(ApiError, response.json())
    assert response.status_code == 403
    assert error.error == "permission_denied"
    _attach_contract("Validated API error", error.model_dump(mode="json"))


@allure.epic("Quality Engineering Lab")
@allure.feature("API Contract")
@allure.story("OpenAPI references")
@pytest.mark.api
@allure.testcase("API-CONTRACT-003", "OpenAPI refs resolve to components")
def test_openapi_references_resolve_to_shared_components(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.get("/openapi.json")

    document = response.json()
    schemas = document["components"]["schemas"]
    references = list(_walk_references(document))
    assert references
    assert all(
        reference.removeprefix("#/components/schemas/") in schemas
        for reference in references
    )
    _attach_contract("Resolved OpenAPI references", references)


def _walk_references(value: Any) -> list[str]:
    references: list[str] = []
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str):
            references.append(reference)
        for item in value.values():
            references.extend(_walk_references(item))
    elif isinstance(value, list):
        for item in value:
            references.extend(_walk_references(item))
    return references
