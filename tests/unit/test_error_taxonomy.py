"""Unit tests for the API failure classification table."""

from __future__ import annotations

import httpx
import pytest
from qa_core.api_errors import classify_error, classify_response


@pytest.mark.parametrize(
    ("status_code", "error_code", "category"),
    [
        (400, "invalid_request", "test"),
        (400, "unsupported_grant_type", "test"),
        (400, "invalid_grant", "auth"),
        (401, "authentication_required", "auth"),
        (401, "invalid_token", "auth"),
        (403, "permission_denied", "permission"),
        (404, "not_found", "product"),
        (404, "workspace_not_found", "product"),
        (404, "item_not_found", "product"),
        (409, "sku_conflict", "product"),
        (409, "idempotency_conflict", "product"),
        (409, "invalid_state_transition", "product"),
        (422, "validation_failed", "product"),
        (429, "rate_limited", "environment"),
        (503, "database_unavailable", "environment"),
    ],
)
def test_exact_error_codes_map_to_expected_category(
    status_code: int,
    error_code: str,
    category: str,
) -> None:
    result = classify_error(status_code, error_code)

    assert result.status_code == status_code
    assert result.error_code == error_code
    assert result.category == category
    assert result.detail


@pytest.mark.parametrize(
    ("status_code", "error_code", "category"),
    [
        (401, None, "auth"),
        (403, "unmapped_code", "permission"),
        (429, None, "environment"),
        (500, "boom", "environment"),
        (503, None, "environment"),
        (400, "brand_new_code", "test"),
        (404, "brand_new_code", "product"),
        (422, "brand_new_code", "product"),
        (418, "teapot", "test"),
    ],
)
def test_unmapped_codes_fall_back_by_status_code(
    status_code: int,
    error_code: str | None,
    category: str,
) -> None:
    assert classify_error(status_code, error_code).category == category


def test_default_error_code_argument_is_optional() -> None:
    result = classify_error(401)

    assert result.error_code is None
    assert result.category == "auth"
    assert result.is_client_error is True


def test_classify_response_reads_error_code_from_json_body() -> None:
    response = httpx.Response(
        409,
        json={"error": "invalid_state_transition", "message": "no"},
    )

    result = classify_response(response)

    assert result.category == "product"
    assert result.error_code == "invalid_state_transition"
    assert result.is_client_error is True


def test_classify_response_handles_non_json_body() -> None:
    response = httpx.Response(503, text="upstream down")

    result = classify_response(response)

    assert result.category == "environment"
    assert result.error_code is None
    assert result.is_client_error is False
