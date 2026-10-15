"""OpenAPI 3.1 document generated from the shared response contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from qa_core.contracts.api import (
    AdminAuditResponse,
    ApiError,
    CacheRefreshRequest,
    CatalogEvent,
    CatalogItem,
    CatalogItemCreate,
    CatalogItemStatusUpdate,
    CatalogResponse,
    FieldError,
    HealthLiveResponse,
    JobAcceptedResponse,
    JobQueueStatsResponse,
    JobResponse,
    OAuthErrorResponse,
    OidcMetadataResponse,
    ReadinessResponse,
    RevokeResponse,
    RootResponse,
    TokenResponse,
    UserResponse,
    ValidationErrorResponse,
)


class _ContractBundle(BaseModel):
    root: RootResponse
    health_live: HealthLiveResponse
    readiness: ReadinessResponse
    oidc_metadata: OidcMetadataResponse
    token: TokenResponse
    user: UserResponse
    admin_audit: AdminAuditResponse
    revoke: RevokeResponse
    catalog: CatalogResponse
    catalog_item: CatalogItem
    catalog_item_create: CatalogItemCreate
    catalog_item_status_update: CatalogItemStatusUpdate
    cache_refresh: CacheRefreshRequest
    job_accepted: JobAcceptedResponse
    job: JobResponse
    job_queue_stats: JobQueueStatsResponse
    catalog_event: CatalogEvent
    api_error: ApiError
    oauth_error: OAuthErrorResponse
    field_error: FieldError
    validation_error: ValidationErrorResponse


def openapi_document() -> dict[str, Any]:
    """Return the local SUT API contract as OpenAPI 3.1 JSON."""

    bundle_schema = _ContractBundle.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    components = bundle_schema.get("$defs", {})
    if not isinstance(components, dict):
        raise TypeError("Pydantic did not produce JSON Schema components")

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Quality Engineering Lab SUT API",
            "version": "0.1.0",
        },
        "paths": {
            "/": {
                "get": _operation(
                    "Read service metadata",
                    RootResponse,
                    error_model=None,
                )
            },
            "/openapi.json": {
                "get": {
                    "summary": "Read the OpenAPI document",
                    "responses": {
                        "200": {
                            "description": "OpenAPI document",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"},
                                }
                            },
                        }
                    },
                }
            },
            "/health/live": {
                "get": _operation(
                    "Read liveness",
                    HealthLiveResponse,
                    error_model=None,
                )
            },
            "/health/ready": {
                "get": _operation(
                    "Read readiness",
                    ReadinessResponse,
                    error_model=ApiError,
                )
            },
            "/.well-known/openid-configuration": {
                "get": _operation(
                    "Read OIDC discovery metadata",
                    OidcMetadataResponse,
                    error_model=ApiError,
                )
            },
            "/oauth/token": {
                "post": {
                    "summary": "Exchange credentials or a refresh token",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["grant_type"],
                                    "properties": {
                                        "grant_type": {
                                            "type": "string",
                                            "enum": [
                                                "password",
                                                "refresh_token",
                                            ],
                                        },
                                        "username": {"type": "string"},
                                        "password": {
                                            "type": "string",
                                            "format": "password",
                                        },
                                        "refresh_token": {"type": "string"},
                                        "scope": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": _response("Token set", TokenResponse),
                        "400": _response("OAuth2 error", OAuthErrorResponse),
                    },
                }
            },
            "/oauth/revoke": {
                "post": {
                    "summary": "Revoke a refresh token",
                    "responses": {
                        "200": _response("Revocation result", RevokeResponse),
                        "400": _response("OAuth2 error", OAuthErrorResponse),
                    },
                }
            },
            "/api/v1/auth/me": {
                "get": {
                    **_operation(
                        "Read the authenticated user",
                        UserResponse,
                        error_model=ApiError,
                    ),
                    "security": [{"bearerAuth": []}],
                }
            },
            "/api/v1/admin/audit": {
                "get": {
                    **_operation(
                        "Read the owner/admin audit summary",
                        AdminAuditResponse,
                        error_model=ApiError,
                    ),
                    "security": [{"bearerAuth": []}],
                }
            },
            "/api/v1/workspaces/{slug}/catalog": {
                "get": {
                    "summary": "Read a workspace catalog",
                    "parameters": [
                        {
                            "name": "slug",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            **_response("Catalog", CatalogResponse),
                            "headers": {
                                "X-Cache": {
                                    "description": (
                                        "Cache state: HIT, MISS, or HIT-NEGATIVE."
                                    ),
                                    "schema": {
                                        "type": "string",
                                        "enum": ["HIT", "MISS", "HIT-NEGATIVE"],
                                    },
                                },
                                "X-Cache-TTL": {
                                    "description": (
                                        "Remaining Redis TTL in seconds; -1 when "
                                        "the entry has no expiry."
                                    ),
                                    "schema": {"type": "integer"},
                                },
                            },
                        },
                        "404": _response("Workspace not found", ApiError),
                        "503": _response("Database unavailable", ApiError),
                    },
                }
            },
            "/api/v1/workspaces/{slug}/catalog/cache/refresh": {
                "post": {
                    "summary": "Queue an asynchronous catalog cache refresh",
                    "security": [{"bearerAuth": []}],
                    "parameters": [_path_parameter("slug")],
                    "requestBody": {
                        **_json_request_body(CacheRefreshRequest),
                        "required": False,
                    },
                    "responses": {
                        "202": _response("Queued job", JobAcceptedResponse),
                        "400": _response("Malformed request", ApiError),
                        "401": _response("Authentication required", ApiError),
                        "403": _response("Permission denied", ApiError),
                        "404": _response("Workspace not found", ApiError),
                        "422": _response(
                            "Request validation failed",
                            ValidationErrorResponse,
                        ),
                    },
                }
            },
            "/api/v1/workspaces/{slug}/events": {
                "get": {
                    "summary": "Subscribe to workspace events over WebSocket",
                    "description": (
                        "RFC 6455 upgrade endpoint. Frames carry the "
                        "CatalogEvent payload. A request without the WebSocket "
                        "upgrade headers is rejected with 426."
                    ),
                    "security": [{"bearerAuth": []}],
                    "parameters": [_path_parameter("slug")],
                    "responses": {
                        "101": {"description": "Switching protocols"},
                        "401": _response("Authentication required", ApiError),
                        "403": _response("Permission denied", ApiError),
                        "404": _response("Workspace not found", ApiError),
                        "426": _response("Upgrade required", ApiError),
                    },
                }
            },
            "/api/v1/jobs": {
                "get": {
                    "summary": "Read background job queue statistics",
                    "security": [{"bearerAuth": []}],
                    "responses": {
                        "200": _response("Queue statistics", JobQueueStatsResponse),
                        "401": _response("Authentication required", ApiError),
                    },
                }
            },
            "/api/v1/jobs/{job_id}": {
                "get": {
                    "summary": "Read one background job",
                    "security": [{"bearerAuth": []}],
                    "parameters": [_path_parameter("job_id")],
                    "responses": {
                        "200": _response("Job record", JobResponse),
                        "401": _response("Authentication required", ApiError),
                        "403": _response("Permission denied", ApiError),
                        "404": _response("Job not found", ApiError),
                    },
                }
            },
            "/api/v1/workspaces/{slug}/catalog/items": {
                "post": {
                    "summary": "Create a catalog item",
                    "security": [{"bearerAuth": []}],
                    "parameters": [
                        _path_parameter("slug"),
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string", "minLength": 1},
                        },
                        {
                            "name": "X-QA-Client-Id",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string", "minLength": 1},
                        },
                    ],
                    "requestBody": _json_request_body(CatalogItemCreate),
                    "responses": {
                        "201": _response("Created catalog item", CatalogItem),
                        "400": _response("Malformed request", ApiError),
                        "401": _response("Authentication required", ApiError),
                        "403": _response("Permission denied", ApiError),
                        "404": _response("Workspace not found", ApiError),
                        "409": _response("Idempotency or SKU conflict", ApiError),
                        "422": _response(
                            "Request validation failed",
                            ValidationErrorResponse,
                        ),
                        "429": _response("Rate limited", ApiError),
                    },
                }
            },
            "/api/v1/workspaces/{slug}/catalog/items/{item_id}": {
                "patch": {
                    "summary": "Transition a catalog item status",
                    "security": [{"bearerAuth": []}],
                    "parameters": [
                        _path_parameter("slug"),
                        _path_parameter("item_id", schema={"type": "integer"}),
                    ],
                    "requestBody": _json_request_body(
                        CatalogItemStatusUpdate,
                    ),
                    "responses": {
                        "200": _response("Updated catalog item", CatalogItem),
                        "400": _response("Malformed request", ApiError),
                        "401": _response("Authentication required", ApiError),
                        "403": _response("Permission denied", ApiError),
                        "404": _response("Item not found", ApiError),
                        "409": _response("Invalid state transition", ApiError),
                        "422": _response(
                            "Request validation failed",
                            ValidationErrorResponse,
                        ),
                    },
                },
                "delete": {
                    "summary": "Delete a catalog item",
                    "security": [{"bearerAuth": []}],
                    "parameters": [
                        _path_parameter("slug"),
                        _path_parameter("item_id", schema={"type": "integer"}),
                    ],
                    "responses": {
                        "204": {"description": "Deleted catalog item"},
                        "401": _response("Authentication required", ApiError),
                        "403": _response("Permission denied", ApiError),
                        "404": _response("Item not found", ApiError),
                    },
                },
            },
        },
        "components": {
            "schemas": components,
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            },
        },
    }


def _operation(
    summary: str,
    model: type[BaseModel],
    *,
    error_model: type[BaseModel] | None,
) -> dict[str, Any]:
    responses: dict[str, Any] = {
        "200": _response(model.__name__, model),
    }
    if error_model is not None:
        responses["400"] = _response("API error", error_model)
    return {
        "summary": summary,
        "responses": responses,
    }


def _response(description: str, model: type[BaseModel]) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {
                    "$ref": f"#/components/schemas/{model.__name__}",
                }
            }
        },
    }


def _json_request_body(model: type[BaseModel]) -> dict[str, Any]:
    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "$ref": f"#/components/schemas/{model.__name__}",
                }
            }
        },
    }


def _path_parameter(
    name: str,
    *,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": schema or {"type": "string"},
    }
