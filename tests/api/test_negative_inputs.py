"""Negative-input contract tests for the local SUT."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import httpx
import pytest
from qa_core.api_errors import classify_response
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.http import HttpClient

from tests.api.conftest import attach_json, items_path, unique_client_id


def _error_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        raw = payload.get("error")
        if isinstance(raw, str):
            return raw
    return None


@pytest.mark.api
@pytest.mark.parametrize(
    ("data", "expected_error"),
    [
        ({"username": "owner@atlas.example"}, "unsupported_grant_type"),
        ({"grant_type": "client_credentials"}, "unsupported_grant_type"),
        ({"grant_type": "password"}, "invalid_request"),
        ({"grant_type": "refresh_token"}, "invalid_request"),
    ],
)
def test_malformed_token_requests_are_rejected(
    sut_api_url: str,
    settings: Settings,
    data: dict[str, str],
    expected_error: str,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.post(settings.auth_token_path, data=data)

    assert response.status_code == 400
    assert _error_code(response) == expected_error
    assert classify_response(response).category == "test"
    attach_json(
        "Rejected token request",
        {"data": data, "status": response.status_code, "body": response.json()},
    )


@pytest.mark.api
def test_password_grant_with_wrong_password_is_invalid_grant(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.post(
            settings.auth_token_path,
            data={
                "grant_type": "password",
                "username": settings.auth_test_username,
                "password": "definitely-not-the-password",
            },
        )

    assert response.status_code == 400
    assert _error_code(response) == "invalid_grant"
    assert classify_response(response).category == "auth"
    attach_json("Invalid grant response", response.json())


@pytest.mark.api
@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"{not-json", "application/json"),
        (b"grant_type=password", "application/xml"),
    ],
)
def test_token_requests_with_broken_bodies_are_invalid_requests(
    sut_api_url: str,
    settings: Settings,
    content: bytes,
    content_type: str,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.post(
            settings.auth_token_path,
            content=content,
            headers={"Content-Type": content_type},
        )

    assert response.status_code == 400
    assert _error_code(response) == "invalid_request"
    attach_json("Broken token body", response.json())


@pytest.mark.api
def test_me_without_credentials_requires_authentication(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert _error_code(response) == "authentication_required"
    assert classify_response(response).category == "auth"
    attach_json("Unauthenticated response", response.json())


@pytest.mark.api
def test_catalog_for_unknown_workspace_is_not_found(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.get("/api/v1/workspaces/does-not-exist/catalog")

    assert response.status_code == 404
    assert _error_code(response) == "workspace_not_found"
    assert classify_response(response).category == "product"
    attach_json("Unknown workspace response", response.json())


@pytest.mark.api
def test_unknown_route_is_not_found(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert _error_code(response) == "not_found"
    attach_json("Unknown route response", response.json())


@pytest.mark.api
@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"{not-json", "application/json"),
        (b"plain text", "text/plain"),
    ],
)
def test_create_item_with_broken_body_is_invalid_request(
    owner_auth: AuthClient,
    content: bytes,
    content_type: str,
) -> None:
    response = owner_auth.post(
        items_path(),
        content=content,
        headers={
            "Content-Type": content_type,
            "X-QA-Client-Id": unique_client_id("neg"),
        },
    )

    assert response.status_code == 400
    assert _error_code(response) == "invalid_request"
    attach_json("Broken create body", response.json())
