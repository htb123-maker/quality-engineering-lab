"""Unit tests for response validation and compatibility decisions."""

from __future__ import annotations

from typing import Any

import pytest
from qa_core.contracts import (
    CatalogItemCreate,
    ContractValidationError,
    HealthLiveResponse,
    TokenResponse,
    compare_json_schemas,
    openapi_document,
    validate_contract,
)


def _object_schema(
    properties: dict[str, dict[str, Any]],
    *,
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def test_contract_validation_reports_missing_field_path() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        validate_contract(
            TokenResponse,
            {
                "access_token": "access",
                "token_type": "Bearer",
                "expires_in": 300,
                "scope": "openid profile",
            },
        )

    assert exc_info.value.model_name == "TokenResponse"
    assert [violation.path for violation in exc_info.value.violations] == [
        "$.refresh_token"
    ]
    assert exc_info.value.violations[0].error_type == "missing"


def test_exact_contract_rejects_unapproved_extra_field() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        validate_contract(
            HealthLiveResponse,
            {"status": "live", "unexpected": True},
        )

    assert exc_info.value.violations[0].path == "$.unexpected"
    assert exc_info.value.violations[0].error_type == "extra_forbidden"


def test_openapi_document_exports_paths_and_shared_components() -> None:
    document = openapi_document()

    assert document["openapi"] == "3.1.0"
    assert {
        "/health/live",
        "/health/ready",
        "/oauth/token",
        "/api/v1/auth/me",
        "/api/v1/admin/audit",
        "/api/v1/workspaces/{slug}/catalog",
    }.issubset(document["paths"])

    schemas = document["components"]["schemas"]
    assert {
        "TokenResponse",
        "UserResponse",
        "CatalogResponse",
        "ApiError",
        "OAuthErrorResponse",
    }.issubset(schemas)
    assert schemas["TokenResponse"]["additionalProperties"] is False


def test_openapi_document_exposes_catalog_write_contracts() -> None:
    document = openapi_document()

    items_path = "/api/v1/workspaces/{slug}/catalog/items"
    item_path = "/api/v1/workspaces/{slug}/catalog/items/{item_id}"
    assert set(document["paths"][items_path]) == {"post"}
    assert set(document["paths"][item_path]) == {"patch", "delete"}
    assert "422" in document["paths"][items_path]["post"]["responses"]

    schemas = document["components"]["schemas"]
    assert {
        "CatalogItemCreate",
        "CatalogItemStatusUpdate",
        "FieldError",
        "ValidationErrorResponse",
    }.issubset(schemas)
    assert schemas["CatalogItemCreate"]["additionalProperties"] is False


def test_catalog_item_create_contract_rejects_negative_price() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        validate_contract(
            CatalogItemCreate,
            {"sku": "QA7W-UNIT-001", "name": "valid", "price_cents": -1},
        )

    assert exc_info.value.model_name == "CatalogItemCreate"
    assert [violation.path for violation in exc_info.value.violations] == [
        "$.price_cents"
    ]


def test_catalog_item_create_contract_rejects_extra_field() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        validate_contract(
            CatalogItemCreate,
            {
                "sku": "QA7W-UNIT-002",
                "name": "valid",
                "price_cents": 100,
                "unexpected": True,
            },
        )

    assert [violation.path for violation in exc_info.value.violations] == [
        "$.unexpected"
    ]


def test_optional_response_field_addition_is_compatible() -> None:
    old_schema = _object_schema(
        {
            "id": {"type": "integer"},
            "name": {"type": "string"},
        },
        required=["id", "name"],
    )
    new_schema = _object_schema(
        {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "nickname": {"type": ["string", "null"]},
        },
        required=["id", "name"],
    )

    report = compare_json_schemas(old_schema, new_schema)

    assert report.compatible is True
    assert len(report.findings) == 1
    assert report.findings[0].severity == "non_breaking"
    assert report.findings[0].path == "$.nickname"
    assert report.findings[0].message == "optional response field was added"


def test_new_required_response_field_is_breaking() -> None:
    old_schema = _object_schema({"id": {"type": "integer"}}, required=["id"])
    new_schema = _object_schema(
        {
            "id": {"type": "integer"},
            "email": {"type": "string"},
        },
        required=["id", "email"],
    )

    report = compare_json_schemas(old_schema, new_schema)

    assert report.compatible is False
    assert report.findings[0].path == "$.email"
    assert report.findings[0].message == "new response field is required"


def test_removed_response_field_is_breaking() -> None:
    old_schema = _object_schema(
        {
            "id": {"type": "integer"},
            "name": {"type": "string"},
        },
        required=["id", "name"],
    )
    new_schema = _object_schema({"id": {"type": "integer"}}, required=["id"])

    report = compare_json_schemas(old_schema, new_schema)

    assert report.compatible is False
    assert report.findings[0].path == "$.name"
    assert report.findings[0].message == "response field was removed"


def test_response_type_change_is_breaking_at_nested_path() -> None:
    old_schema = _object_schema(
        {"workspace": _object_schema({"id": {"type": "integer"}}, required=["id"])},
        required=["workspace"],
    )
    new_schema = _object_schema(
        {"workspace": _object_schema({"id": {"type": "string"}}, required=["id"])},
        required=["workspace"],
    )

    report = compare_json_schemas(old_schema, new_schema)

    assert report.compatible is False
    assert report.findings[0].path == "$.workspace.id"
    assert "type changed" in report.findings[0].message


def test_enum_removal_is_breaking_and_addition_is_non_breaking() -> None:
    old_schema = _object_schema(
        {"role": {"type": "string", "enum": ["owner", "viewer"]}},
        required=["role"],
    )
    new_schema = _object_schema(
        {"role": {"type": "string", "enum": ["owner", "admin"]}},
        required=["role"],
    )

    report = compare_json_schemas(old_schema, new_schema)

    assert report.compatible is False
    assert {finding.severity for finding in report.findings} == {
        "breaking",
        "non_breaking",
    }
    assert any(
        "enum values were removed" in finding.message
        for finding in report.findings
    )
