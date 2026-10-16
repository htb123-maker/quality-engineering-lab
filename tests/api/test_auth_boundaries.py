"""Authentication boundary tests driven by crafted local JWTs."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from qa_core.auth import encode_hs256_jwt
from qa_core.config.settings import Settings
from qa_core.http import HttpClient

from tests.api.conftest import attach_json


def _claims(settings: Settings, *, now: int, **overrides: Any) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "iss": settings.auth_issuer,
        "sub": "1",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return claims


def _call_me(settings: Settings, token: str, *, scheme: str = "Bearer") -> httpx.Response:
    with HttpClient.from_settings(settings) as client:
        return client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"{scheme} {token}"},
        )


@pytest.mark.api
def test_correctly_crafted_token_is_accepted(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    now = int(time.time())
    token = encode_hs256_jwt(
        _claims(settings, now=now),
        secret=settings.auth_jwt_secret,
    )

    response = _call_me(settings, token)

    assert response.status_code == 200
    assert response.json()["id"] == 1


@pytest.mark.api
def test_expired_token_is_rejected(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    now = int(time.time())
    token = encode_hs256_jwt(
        _claims(settings, now=now, exp=now - 1),
        secret=settings.auth_jwt_secret,
    )

    response = _call_me(settings, token)

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"
    attach_json(
        "Expired token result",
        {"claim_exp": now - 1, "status": response.status_code},
    )


@pytest.mark.api
def test_token_with_wrong_issuer_is_rejected(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    now = int(time.time())
    token = encode_hs256_jwt(
        _claims(settings, now=now, iss="some-other-issuer"),
        secret=settings.auth_jwt_secret,
    )

    response = _call_me(settings, token)

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"


@pytest.mark.api
def test_token_with_forged_signature_is_rejected(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    now = int(time.time())
    token = encode_hs256_jwt(
        _claims(settings, now=now),
        secret="a-different-signing-secret",
    )

    response = _call_me(settings, token)

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"


@pytest.mark.api
def test_token_without_subject_is_rejected(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    now = int(time.time())
    claims = _claims(settings, now=now)
    claims.pop("sub")
    token = encode_hs256_jwt(claims, secret=settings.auth_jwt_secret)

    response = _call_me(settings, token)

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"


@pytest.mark.api
def test_non_bearer_scheme_is_treated_as_missing_credentials(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    now = int(time.time())
    token = encode_hs256_jwt(
        _claims(settings, now=now),
        secret=settings.auth_jwt_secret,
    )

    response = _call_me(settings, token, scheme="Basic")

    assert response.status_code == 401
    assert response.json()["error"] == "authentication_required"
    attach_json("Non-bearer scheme", response.json())
