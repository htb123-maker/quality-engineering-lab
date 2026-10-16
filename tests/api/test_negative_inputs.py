"""Negative-input contract tests for the local SUT."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import httpx
import pytest
from qa_core.api_errors import classify_response
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.http import HttpClient
from qa_core.resource_pools import NamespaceLease

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
    ("content", "content_type", "expected_status", "expected_error"),
    [
        (b"{not-json", "application/json", 400, "invalid_request"),
        # Week 11 split "malformed body" (400) from "media type this endpoint
        # does not read" (415).
        (b"plain text", "text/plain", 415, "unsupported_media_type"),
    ],
)
def test_create_item_with_broken_body_is_invalid_request(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    content: bytes,
    content_type: str,
    expected_status: int,
    expected_error: str,
) -> None:
    response = owner_auth.post(
        items_path(namespace.slug),
        content=content,
        headers={
            "Content-Type": content_type,
            "X-QA-Client-Id": unique_client_id("neg"),
        },
    )

    assert response.status_code == expected_status
    assert _error_code(response) == expected_error
    attach_json("Broken create body", response.json())


@pytest.mark.api
@pytest.mark.parametrize(
    ("authorization", "expected_status", "expected_error"),
    [
        (None, 401, "authentication_required"),
        ("Basic YmFkOmJhZA==", 401, "authentication_required"),
        ("Bearer not-a-jwt", 401, "invalid_token"),
    ],
)
def test_catalog_write_requires_valid_authentication(
    sut_api_url: str,
    settings: Settings,
    namespace: NamespaceLease,
    authorization: str | None,
    expected_status: int,
    expected_error: str,
) -> None:
    del sut_api_url

    headers = {"X-QA-Client-Id": unique_client_id("anon")}
    if authorization is not None:
        headers["Authorization"] = authorization
    with HttpClient.from_settings(settings) as client:
        response = client.post(
            items_path(namespace.slug),
            json={"sku": "QA8-ANON-001", "name": "anon", "price_cents": 100},
            headers=headers,
        )

    assert response.status_code == expected_status
    assert _error_code(response) == expected_error
    assert classify_response(response).category == "auth"
    attach_json(
        "Unauthenticated write",
        {"authorization": authorization, "body": response.json()},
    )


@pytest.mark.api
def test_read_on_the_item_path_requires_authentication(
    sut_api_url: str,
    settings: Settings,
    namespace: NamespaceLease,
) -> None:
    """Week 11 added GET on the item path, replacing Week 7's "no route"."""

    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.get(f"{items_path(namespace.slug)}/1")

    assert response.status_code == 401
    assert _error_code(response) == "authentication_required"
    attach_json("Item read without credentials", response.json())


@pytest.mark.api
def test_create_in_unknown_workspace_is_not_found(
    owner_auth: AuthClient,
) -> None:
    response = owner_auth.post(
        items_path("does-not-exist"),
        json={"sku": "QA8-GHOST-001", "name": "ghost", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id("ghost")},
    )

    assert response.status_code == 404
    assert _error_code(response) == "workspace_not_found"
    assert classify_response(response).category == "product"
    attach_json("Unknown workspace write", response.json())


@pytest.mark.api
def test_delete_of_unknown_item_is_not_found(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    response = owner_auth.request(
        "DELETE",
        f"{items_path(namespace.slug)}/2000000000",
        headers={"X-QA-Client-Id": unique_client_id("missing")},
    )

    assert response.status_code == 404
    assert _error_code(response) == "item_not_found"
    attach_json("Missing item delete", response.json())


@pytest.mark.api
def test_patch_with_broken_body_is_invalid_request(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    response = owner_auth.request(
        "PATCH",
        f"{items_path(namespace.slug)}/1",
        content=b"{not-json",
        headers={
            "Content-Type": "application/json",
            "X-QA-Client-Id": unique_client_id("patch"),
        },
    )

    assert response.status_code == 400
    assert _error_code(response) == "invalid_request"
    attach_json("Broken patch body", response.json())


@pytest.mark.api
@pytest.mark.xfail(
    reason=(
        "The SUT falls through to BaseHTTPRequestHandler's HTML 501 page "
        "instead of the shared JSON error contract for unsupported methods."
    ),
    strict=True,
)
def test_unsupported_method_returns_the_json_error_contract(
    sut_api_url: str,
    settings: Settings,
    namespace: NamespaceLease,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.request(
            "PUT",
            items_path(namespace.slug),
            json={"sku": "QA8-PUT-001", "name": "put", "price_cents": 100},
        )

    assert response.status_code in {404, 405, 501}
    assert _error_code(response) in {"not_found", "method_not_allowed"}
