"""Live authentication contract tests for the local SUT."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import json

import allure
import pytest
from qa_core.auth import AuthClient, decode_jwt_claims_unverified
from qa_core.config.settings import Settings
from qa_core.http import HttpClient


def _attach_json(name: str, payload: object) -> None:
    allure.attach(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("Authentication")
@allure.story("OIDC discovery and password login")
@pytest.mark.api
@allure.testcase("API-AUTH-001", "OIDC discovery and bearer login")
def test_oidc_discovery_and_bearer_login(
    sut_api_url: str,
    settings: Settings,
) -> None:
    with AuthClient.from_settings(settings) as client:
        metadata = client.discover()
        tokens = client.login(
            settings.auth_test_username,
            settings.auth_test_password,
        )
        me = client.get("/api/v1/auth/me")
        audit = client.get("/api/v1/admin/audit")

    assert str(settings.api_base_url).rstrip("/") == sut_api_url
    assert metadata.issuer == "quality-engineering-lab-local"
    assert metadata.token_endpoint == "/oauth/token"
    assert tokens.expires_at > 0
    assert decode_jwt_claims_unverified(tokens.access_token)["role"] == "owner"
    assert me.status_code == 200
    assert me.json()["email"] == settings.auth_test_username
    assert me.json()["role"] == "owner"
    assert audit.status_code == 200
    assert audit.json()["role"] == "owner"
    _attach_json("OIDC discovery", metadata.model_dump())
    _attach_json("Authenticated user", me.json())
    _attach_json("Authorized audit access", audit.json())


@allure.epic("Quality Engineering Lab")
@allure.feature("Authentication")
@allure.story("Role authorization")
@pytest.mark.api
@allure.testcase("API-AUTH-002", "Viewer receives permission denied")
def test_viewer_is_authenticated_but_cannot_read_admin_audit(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with AuthClient.from_settings(settings) as client:
        client.login("viewer@atlas.example", settings.auth_test_password)
        me = client.get("/api/v1/auth/me")
        audit = client.get("/api/v1/admin/audit")

    assert me.status_code == 200
    assert me.json()["role"] == "viewer"
    assert audit.status_code == 403
    assert audit.json()["error"] == "permission_denied"
    _attach_json("Permission denied response", audit.json())


@allure.epic("Quality Engineering Lab")
@allure.feature("Authentication")
@allure.story("Refresh token rotation")
@pytest.mark.api
@allure.testcase("API-AUTH-003", "Refresh token rotates exactly once")
def test_refresh_token_rotation_rejects_replay(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with AuthClient.from_settings(settings) as client:
        original = client.login(
            settings.auth_test_username,
            settings.auth_test_password,
        )
        rotated = client.refresh()
        me = client.get("/api/v1/auth/me")

    with HttpClient.from_settings(settings) as raw_client:
        replay = raw_client.post(
            settings.auth_token_path,
            data={
                "grant_type": "refresh_token",
                "refresh_token": original.refresh_token,
            },
        )

    assert rotated.access_token != original.access_token
    assert rotated.refresh_token != original.refresh_token
    assert me.status_code == 200
    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"
    _attach_json("Refresh replay response", replay.json())


@allure.epic("Quality Engineering Lab")
@allure.feature("Authentication")
@allure.story("HttpOnly cookie session")
@pytest.mark.api
@allure.testcase("API-AUTH-004", "Cookie mode authenticates without bearer header")
def test_cookie_mode_authenticates_me_endpoint(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with AuthClient.from_settings(settings, mode="cookie") as client:
        client.login(
            settings.auth_test_username,
            settings.auth_test_password,
        )
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == settings.auth_test_username
    _attach_json("Cookie-authenticated user", response.json())


@allure.epic("Quality Engineering Lab")
@allure.feature("Authentication")
@allure.story("Logout revocation")
@pytest.mark.api
@allure.testcase("API-AUTH-005", "Logout revokes the refresh token")
def test_logout_revokes_refresh_token(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with AuthClient.from_settings(settings) as client:
        tokens = client.login(
            settings.auth_test_username,
            settings.auth_test_password,
        )
        client.logout()

    with HttpClient.from_settings(settings) as raw_client:
        replay = raw_client.post(
            settings.auth_token_path,
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens.refresh_token,
            },
        )

    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"
    _attach_json("Revoked token response", replay.json())
