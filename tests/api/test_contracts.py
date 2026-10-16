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
    CatalogItem,
    CatalogResponse,
    OidcMetadataResponse,
    ReadinessResponse,
    TokenResponse,
    UserResponse,
    ValidationErrorResponse,
    openapi_document,
    validate_contract,
)
from qa_core.data_factories import CatalogApiFactory, items_path
from qa_core.http import HttpClient
from qa_core.resource_pools import NamespaceLease


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


@allure.epic("Quality Engineering Lab")
@allure.feature("API Contract")
@allure.story("Catalog write responses")
@pytest.mark.api
@allure.testcase("API-CONTRACT-004", "Create and patch return the item contract")
def test_catalog_item_write_responses_match_the_item_contract(
    catalog_items: CatalogApiFactory,
) -> None:
    created = catalog_items.create()
    item = validate_contract(CatalogItem, created.json())

    archived = catalog_items.set_status(item.id, "archived")
    updated = validate_contract(CatalogItem, archived.json())

    assert created.status_code == 201
    assert updated.id == item.id
    assert updated.status == "archived"
    _attach_contract(
        "Catalog item contract",
        {"created": item.model_dump(mode="json"), "patched": updated.model_dump(mode="json")},
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("API Contract")
@allure.story("Error contract")
@pytest.mark.api
@allure.testcase("API-CONTRACT-005", "404 responses match the error contract")
def test_not_found_error_matches_the_error_contract(
    sut_api_url: str,
    settings: Settings,
    namespace: NamespaceLease,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.get(f"/api/v1/workspaces/{namespace.slug}-missing/catalog")

    error = validate_contract(ApiError, response.json())
    assert response.status_code == 404
    assert error.error == "workspace_not_found"
    _attach_contract("Not-found error", error.model_dump(mode="json"))


@allure.epic("Quality Engineering Lab")
@allure.feature("API Contract")
@allure.story("Validation contract")
@pytest.mark.api
@allure.testcase("API-CONTRACT-006", "422 responses match the validation contract")
def test_validation_error_matches_the_validation_contract(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    response = owner_auth.post(
        items_path(namespace.slug),
        json={"sku": "QA", "name": "", "price_cents": -5},
        headers={"X-QA-Client-Id": "qa8-contract-validation"},
    )

    validation = validate_contract(ValidationErrorResponse, response.json())
    assert response.status_code == 422
    assert validation.error == "validation_failed"
    assert {field.field for field in validation.fields} == {
        "$.sku",
        "$.name",
        "$.price_cents",
    }
    _attach_contract(
        "Validation contract",
        validation.model_dump(mode="json"),
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("API Contract")
@allure.story("OpenAPI write operations")
@pytest.mark.api
@allure.testcase("API-CONTRACT-007", "OpenAPI documents catalog write operations")
def test_openapi_documents_the_catalog_write_operations(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        document = client.get("/openapi.json").json()

    collection = document["paths"]["/api/v1/workspaces/{slug}/catalog/items"]
    item = document["paths"]["/api/v1/workspaces/{slug}/catalog/items/{item_id}"]

    assert "post" in collection
    assert collection["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert {"patch", "delete"} <= set(item)
    schemas = document["components"]["schemas"]
    assert {"CatalogItem", "CatalogItemCreate", "ValidationErrorResponse"} <= set(schemas)
    _attach_contract(
        "Catalog write operations",
        {"collection": sorted(collection), "item": sorted(item)},
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("API Contract")
@allure.story("Readiness contract")
@pytest.mark.api
@allure.testcase("API-CONTRACT-008", "Readiness response matches the readiness contract")
def test_readiness_response_matches_the_readiness_contract(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.get("/health/ready")

    readiness = validate_contract(ReadinessResponse, response.json())
    assert readiness.status == "ready"
    assert set(readiness.checks) == {"postgres", "redis"}
    assert all(check.status == "ok" for check in readiness.checks.values())
    _attach_contract("Readiness contract", readiness.model_dump(mode="json"))
