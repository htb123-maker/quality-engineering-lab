"""Classify SUT error responses into a stable failure source category.

Every API failure should point at one owner: the product, the test, the
authentication layer, the permission layer, or the environment. Tests attach
this classification to Allure so a red run says who should look next.
"""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

ErrorCategory = Literal["product", "test", "auth", "permission", "environment"]


class ErrorClassification(BaseModel):
    """One classified error response with its owning category."""

    model_config = ConfigDict(frozen=True)

    status_code: int
    error_code: str | None
    category: ErrorCategory
    detail: str

    @property
    def is_client_error(self) -> bool:
        """Return whether the status code is in the 4xx range."""

        return 400 <= self.status_code < 500


_EXACT: dict[tuple[int, str], tuple[ErrorCategory, str]] = {
    (400, "invalid_request"): (
        "test",
        "The request body or content type was malformed before reaching "
        "business rules.",
    ),
    (400, "unsupported_grant_type"): (
        "test",
        "The test asked for a grant type the server does not implement.",
    ),
    (400, "invalid_workspace_slug"): (
        "test",
        "The workspace slug is not a legal identifier, so it was never "
        "resolved against the database.",
    ),
    (400, "invalid_grant"): (
        "auth",
        "Credentials or the refresh token were rejected by the auth layer.",
    ),
    (401, "authentication_required"): (
        "auth",
        "No usable credential was presented.",
    ),
    (401, "invalid_token"): (
        "auth",
        "The presented access token is expired, forged, or otherwise invalid.",
    ),
    (403, "permission_denied"): (
        "permission",
        "The caller is authenticated but lacks the required role or scope.",
    ),
    (403, "owner_protected"): (
        "permission",
        "The request tried to modify an owner row through the members API.",
    ),
    (403, "role_escalation_forbidden"): (
        "permission",
        "The caller tried to grant a role above its own authority.",
    ),
    (403, "self_modification_forbidden"): (
        "permission",
        "The caller tried to change or remove its own membership.",
    ),
    (404, "not_found"): (
        "product",
        "No route matches the request.",
    ),
    (404, "workspace_not_found"): (
        "product",
        "The workspace referenced by the request does not exist.",
    ),
    (404, "item_not_found"): (
        "product",
        "The catalog item referenced by the request does not exist.",
    ),
    (404, "member_not_found"): (
        "product",
        "The member referenced by the request does not exist in this workspace.",
    ),
    (409, "sku_conflict"): (
        "product",
        "The SKU already exists in this workspace.",
    ),
    (409, "idempotency_conflict"): (
        "product",
        "The same idempotency key was reused with a different request body.",
    ),
    (409, "invalid_state_transition"): (
        "product",
        "The requested state change is not allowed by the item's state machine.",
    ),
    (409, "member_conflict"): (
        "product",
        "The email already belongs to this workspace.",
    ),
    (413, "payload_too_large"): (
        "test",
        "The request body exceeded the configured size budget.",
    ),
    (415, "unsupported_media_type"): (
        "test",
        "The request body was sent with a media type the endpoint does not read.",
    ),
    (422, "validation_failed"): (
        "product",
        "The request is well formed but violates the documented field rules.",
    ),
    (429, "rate_limited"): (
        "environment",
        "The caller exceeded the configured request budget.",
    ),
    (503, "database_unavailable"): (
        "environment",
        "A required backing service is unavailable.",
    ),
}


def classify_error(
    status_code: int,
    error_code: str | None = None,
) -> ErrorClassification:
    """Classify one status code and error code into a failure category."""

    if error_code is not None:
        exact = _EXACT.get((status_code, error_code))
        if exact is not None:
            category, detail = exact
            return ErrorClassification(
                status_code=status_code,
                error_code=error_code,
                category=category,
                detail=detail,
            )

    category, detail = _fallback(status_code)
    return ErrorClassification(
        status_code=status_code,
        error_code=error_code,
        category=category,
        detail=detail,
    )


def classify_response(response: httpx.Response) -> ErrorClassification:
    """Classify an HTTP response, reading the error code from its JSON body."""

    error_code: str | None = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        raw_error = payload.get("error")
        if isinstance(raw_error, str):
            error_code = raw_error

    return classify_error(response.status_code, error_code)


def _fallback(status_code: int) -> tuple[ErrorCategory, str]:
    if status_code == 401:
        return "auth", "Unauthenticated response without a mapped error code."
    if status_code == 403:
        return "permission", "Forbidden response without a mapped error code."
    if status_code == 429 or status_code >= 500:
        return "environment", "Server or infrastructure side failure."
    if status_code in {404, 409, 422}:
        return "product", "Unclassified product rule rejection."
    if 400 <= status_code < 500:
        return "test", "Unclassified client error, usually an unexpected test input."
    return "test", "Unexpected status code outside the documented contract."
