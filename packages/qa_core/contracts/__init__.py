"""Shared API response contracts, validation, and compatibility helpers."""

from qa_core.contracts.api import (
    AdminAuditResponse,
    ApiError,
    CatalogItem,
    CatalogResponse,
    CatalogWorkspace,
    ContractModel,
    HealthCheck,
    HealthLiveResponse,
    OAuthErrorResponse,
    OidcMetadataResponse,
    ReadinessResponse,
    RevokeResponse,
    RootResponse,
    TokenResponse,
    UserResponse,
)
from qa_core.contracts.compatibility import (
    CompatibilityFinding,
    CompatibilityReport,
    compare_json_schemas,
)
from qa_core.contracts.openapi import openapi_document
from qa_core.contracts.validation import (
    ContractValidationError,
    FieldViolation,
    validate_contract,
)

__all__ = [
    "AdminAuditResponse",
    "ApiError",
    "CatalogItem",
    "CatalogResponse",
    "CatalogWorkspace",
    "CompatibilityFinding",
    "CompatibilityReport",
    "ContractModel",
    "ContractValidationError",
    "FieldViolation",
    "HealthCheck",
    "HealthLiveResponse",
    "OAuthErrorResponse",
    "OidcMetadataResponse",
    "ReadinessResponse",
    "RevokeResponse",
    "RootResponse",
    "TokenResponse",
    "UserResponse",
    "compare_json_schemas",
    "openapi_document",
    "validate_contract",
]
