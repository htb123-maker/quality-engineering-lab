"""Unit tests for authentication state, refresh, and cookie behavior."""

from __future__ import annotations

import base64
import json
import threading
from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest
from qa_core.auth import (
    AuthClient,
    AuthenticationRequired,
    RefreshTokenInvalid,
    decode_jwt_claims_unverified,
)
from qa_core.http import HttpClient

RequestHandler = Callable[[httpx.Request], httpx.Response]


def _client(handler: RequestHandler, *, now: list[float]) -> HttpClient:
    return HttpClient(
        base_url="https://auth.example.test",
        transport=httpx.MockTransport(handler),
    )


def _token_payload(
    access_token: str,
    refresh_token: str,
    *,
    expires_in: int = 60,
) -> dict[str, object]:
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": "openid profile",
    }


def _form(request: httpx.Request) -> dict[str, str]:
    fields = parse_qs(request.content.decode("utf-8"), keep_blank_values=True)
    return {name: values[-1] for name, values in fields.items()}


def test_login_and_authenticated_request_use_bearer_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            assert _form(request) == {
                "grant_type": "password",
                "username": "owner@atlas.example",
                "password": "local-test-password",
                "scope": "openid profile",
            }
            return httpx.Response(
                200,
                json=_token_payload("access-1", "refresh-1"),
                request=request,
            )
        assert request.url.path == "/api/v1/auth/me"
        assert request.headers["Authorization"] == "Bearer access-1"
        return httpx.Response(200, json={"sub": "1"}, request=request)

    auth = AuthClient(
        _client(handler, now=[100.0]),
        time_source=lambda: 100.0,
    )
    try:
        tokens = auth.login("owner@atlas.example", "local-test-password")
        response = auth.get("/api/v1/auth/me")
    finally:
        auth.close()

    assert response.status_code == 200
    assert tokens.access_token == "access-1"
    assert tokens.refresh_token == "refresh-1"
    assert tokens.expires_at == 160.0


def test_expired_token_refresh_is_single_flight() -> None:
    now = [100.0]
    refresh_attempts = 0
    refresh_started = threading.Event()
    release_refresh = threading.Event()
    barrier = threading.Barrier(3)
    thread_state = threading.local()

    def time_source() -> float:
        if not getattr(thread_state, "coordinated", False):
            thread_state.coordinated = True
            if now[0] > 100.0:
                barrier.wait(timeout=2)
        return now[0]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal refresh_attempts
        if request.url.path == "/oauth/token":
            fields = _form(request)
            if fields["grant_type"] == "password":
                return httpx.Response(
                    200,
                    json=_token_payload("access-1", "refresh-1", expires_in=1),
                    request=request,
                )

            refresh_attempts += 1
            refresh_started.set()
            assert release_refresh.wait(timeout=2)
            return httpx.Response(
                200,
                json=_token_payload("access-2", "refresh-2"),
                request=request,
            )

        return httpx.Response(200, json={"ok": True}, request=request)

    auth = AuthClient(
        _client(handler, now=now),
        time_source=time_source,
    )
    try:
        auth.login("owner@atlas.example", "local-test-password")
        now[0] = 102.0
        responses: list[httpx.Response] = []
        errors: list[BaseException] = []

        def request_protected() -> None:
            try:
                responses.append(auth.get("/api/v1/protected"))
            except BaseException as exc:  # pragma: no cover - diagnostic capture
                errors.append(exc)

        threads = [threading.Thread(target=request_protected) for _ in range(3)]
        for thread in threads:
            thread.start()

        assert refresh_started.wait(timeout=2)
        release_refresh.set()
        for thread in threads:
            thread.join(timeout=2)
            assert thread.is_alive() is False
    finally:
        auth.close()

    assert errors == []
    assert len(responses) == 3
    assert refresh_attempts == 1
    assert auth.tokens is not None
    assert auth.tokens.access_token == "access-2"


def test_reactive_401_refresh_retries_request_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/oauth/token":
            fields = _form(request)
            if fields["grant_type"] == "password":
                return httpx.Response(
                    200,
                    json=_token_payload("access-1", "refresh-1"),
                    request=request,
                )
            return httpx.Response(
                200,
                json=_token_payload("access-2", "refresh-2"),
                request=request,
            )

        attempts += 1
        if request.headers["Authorization"] == "Bearer access-1":
            return httpx.Response(401, json={"error": "expired"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    auth = AuthClient(
        _client(handler, now=[100.0]),
        time_source=lambda: 100.0,
    )
    try:
        auth.login("owner@atlas.example", "local-test-password")
        response = auth.get("/api/v1/protected")
    finally:
        auth.close()

    assert response.status_code == 200
    assert attempts == 2


def test_refresh_failure_clears_local_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            fields = _form(request)
            if fields["grant_type"] == "password":
                return httpx.Response(
                    200,
                    json=_token_payload("access-1", "refresh-1", expires_in=1),
                    request=request,
                )
            return httpx.Response(
                400,
                json={
                    "error": "invalid_grant",
                    "error_description": "refresh token was already used",
                },
                request=request,
            )
        raise AssertionError("protected request must not run after refresh failure")

    now = [100.0]
    auth = AuthClient(
        _client(handler, now=now),
        time_source=lambda: now[0],
    )
    try:
        auth.login("owner@atlas.example", "local-test-password")
        now[0] = 102.0
        with pytest.raises(RefreshTokenInvalid):
            auth.get("/api/v1/protected")
        assert auth.tokens is None
        with pytest.raises(AuthenticationRequired):
            auth.get("/api/v1/protected")
    finally:
        auth.close()


def test_cookie_mode_uses_cookie_jar_without_authorization_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(
                200,
                json=_token_payload("access-1", "refresh-1"),
                headers={
                    "Set-Cookie": (
                        "qa_access_token=access-1; Path=/; HttpOnly; SameSite=Lax"
                    )
                },
                request=request,
            )

        assert request.headers.get("Authorization") is None
        assert request.headers["Cookie"] == "qa_access_token=access-1"
        return httpx.Response(200, json={"authenticated": True}, request=request)

    auth = AuthClient(
        _client(handler, now=[100.0]),
        mode="cookie",
        time_source=lambda: 100.0,
    )
    try:
        auth.login("owner@atlas.example", "local-test-password")
        response = auth.get("/api/v1/auth/me")
    finally:
        auth.close()

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


def test_discovery_returns_oidc_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/.well-known/openid-configuration"
        return httpx.Response(
            200,
            json={
                "issuer": "quality-engineering-lab-local",
                "token_endpoint": "/oauth/token",
                "userinfo_endpoint": "/api/v1/auth/me",
                "revocation_endpoint": "/oauth/revoke",
                "grant_types_supported": ["password", "refresh_token"],
            },
            request=request,
        )

    auth = AuthClient(_client(handler, now=[100.0]))
    try:
        metadata = auth.discover()
    finally:
        auth.close()

    assert metadata.issuer == "quality-engineering-lab-local"
    assert metadata.userinfo_endpoint == "/api/v1/auth/me"
    assert metadata.grant_types_supported == ("password", "refresh_token")


def test_decode_jwt_claims_unverified_reads_expiry() -> None:
    payload = {"sub": "42", "exp": 1_700_000_000, "role": "viewer"}
    encoded_payload = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    token = f"header.{encoded_payload}.signature"

    assert decode_jwt_claims_unverified(token) == payload
