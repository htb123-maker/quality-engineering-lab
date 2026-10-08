"""Small local API with read-only business data and auth session state."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import psycopg
import redis
from psycopg.rows import dict_row

POSTGRES_DSN = os.getenv(
    "QA_POSTGRES_DSN",
    "postgresql://qa:qa@postgres:5432/qa",
)
REDIS_URL = os.getenv("QA_REDIS_URL", "redis://redis:6379/0")
LOG_LEVEL = os.getenv("QA_LOG_LEVEL", "INFO").upper()
AUTH_TEST_PASSWORD = os.getenv("QA_AUTH_TEST_PASSWORD", "local-test-password")
AUTH_JWT_SECRET = os.getenv(
    "QA_AUTH_JWT_SECRET",
    "local-sut-jwt-secret-not-for-production",
).encode("utf-8")
AUTH_ISSUER = os.getenv("QA_AUTH_ISSUER", "quality-engineering-lab-local")
AUTH_ACCESS_TOKEN_TTL_SECONDS = int(
    os.getenv("QA_AUTH_ACCESS_TOKEN_TTL_SECONDS", "300")
)
AUTH_REFRESH_TOKEN_TTL_SECONDS = int(
    os.getenv("QA_AUTH_REFRESH_TOKEN_TTL_SECONDS", "3600")
)
CATALOG_PATH = re.compile(r"^/api/v1/workspaces/([^/]+)/catalog$")

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("sut-api")


def _postgres_check() -> dict[str, Any]:
    with psycopg.connect(POSTGRES_DSN, connect_timeout=2) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            row = cursor.fetchone()

    return {
        "status": "ok",
        "database": row[0] if row else None,
        "user": row[1] if row else None,
    }


def _redis_check() -> dict[str, Any]:
    client = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        pong = client.ping()
    finally:
        client.close()

    return {"status": "ok", "ping": bool(pong)}


def _auth_redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def _find_user_by_email(email: str) -> dict[str, Any] | None:
    with psycopg.connect(POSTGRES_DSN, connect_timeout=2) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    u.id,
                    u.workspace_id,
                    u.email,
                    u.display_name,
                    u.role,
                    u.status,
                    w.slug AS workspace_slug
                FROM users AS u
                JOIN workspaces AS w ON w.id = u.workspace_id
                WHERE u.email = %s
                """,
                (email,),
            )
            return cursor.fetchone()


def _find_user_by_id(user_id: int) -> dict[str, Any] | None:
    with psycopg.connect(POSTGRES_DSN, connect_timeout=2) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    u.id,
                    u.workspace_id,
                    u.email,
                    u.display_name,
                    u.role,
                    u.status,
                    w.slug AS workspace_slug
                FROM users AS u
                JOIN workspaces AS w ON w.id = u.workspace_id
                WHERE u.id = %s
                """,
                (user_id,),
            )
            return cursor.fetchone()


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _issue_access_token(user: dict[str, Any], *, now: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "jti": secrets.token_urlsafe(16),
        "iss": AUTH_ISSUER,
        "sub": str(user["id"]),
        "email": user["email"],
        "workspace_id": user["workspace_id"],
        "role": user["role"],
        "iat": now,
        "exp": now + AUTH_ACCESS_TOKEN_TTL_SECONDS,
    }
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(AUTH_JWT_SECRET, signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"


def _decode_access_token(token: str, *, now: int) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("access token must contain three segments")

    encoded_header, encoded_payload, encoded_signature = parts
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature = hmac.new(
        AUTH_JWT_SECRET,
        signing_input,
        hashlib.sha256,
    ).digest()
    padding = "=" * (-len(encoded_signature) % 4)
    supplied_signature = base64.urlsafe_b64decode(encoded_signature + padding)
    if not hmac.compare_digest(expected_signature, supplied_signature):
        raise ValueError("access token signature is invalid")

    payload_padding = "=" * (-len(encoded_payload) % 4)
    payload = json.loads(
        base64.urlsafe_b64decode(encoded_payload + payload_padding).decode("utf-8")
    )
    if not isinstance(payload, dict):
        raise ValueError("access token payload must be a JSON object")
    if payload.get("iss") != AUTH_ISSUER:
        raise ValueError("access token issuer is invalid")
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at <= now:
        raise ValueError("access token is expired or has no valid exp claim")
    return payload


def _refresh_key(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"auth:refresh:{digest}"


def _create_refresh_token(user: dict[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    client = _auth_redis_client()
    try:
        client.setex(
            _refresh_key(token),
            AUTH_REFRESH_TOKEN_TTL_SECONDS,
            str(user["id"]),
        )
    finally:
        client.close()
    return token


def _consume_refresh_token(token: str) -> int | None:
    client = _auth_redis_client()
    try:
        user_id = client.getdel(_refresh_key(token))
    finally:
        client.close()

    if user_id is None:
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


def _revoke_refresh_token(token: str) -> None:
    client = _auth_redis_client()
    try:
        client.delete(_refresh_key(token))
    finally:
        client.close()


def _authenticate_password(username: str, password: str) -> dict[str, Any] | None:
    if not hmac.compare_digest(password, AUTH_TEST_PASSWORD):
        return None
    user = _find_user_by_email(username)
    if user is None or user["status"] != "active":
        return None
    return user


def _token_response(user: dict[str, Any]) -> tuple[dict[str, Any], str]:
    now = int(time.time())
    access_token = _issue_access_token(user, now=now)
    refresh_token = _create_refresh_token(user)
    return (
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": AUTH_ACCESS_TOKEN_TTL_SECONDS,
            "scope": "openid profile",
        },
        refresh_token,
    )


def _user_payload(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "workspace_id": user["workspace_id"],
        "workspace_slug": user["workspace_slug"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
        "status": user["status"],
    }


def _catalog_payload(slug: str) -> tuple[int, dict[str, Any]]:
    with psycopg.connect(POSTGRES_DSN, connect_timeout=2) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, slug, name
                FROM workspaces
                WHERE slug = %s
                """,
                (slug,),
            )
            workspace = cursor.fetchone()
            if workspace is None:
                return HTTPStatus.NOT_FOUND, {
                    "error": "workspace_not_found",
                    "message": f"Workspace '{slug}' was not found.",
                }

            cursor.execute(
                """
                SELECT id, sku, name, price_cents, status
                FROM catalog_items
                WHERE workspace_id = %s
                ORDER BY id
                """,
                (workspace["id"],),
            )
            items = cursor.fetchall()

    return HTTPStatus.OK, {
        "workspace": {
            "slug": workspace["slug"],
            "name": workspace["name"],
        },
        "items": items,
        "count": len(items),
    }


class SutRequestHandler(BaseHTTPRequestHandler):
    """Serve health, read-only catalog, and local authentication endpoints."""

    server_version = "QualityLabSut/0.1"

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/":
            self._send_json(
                HTTPStatus.OK,
                {
                    "service": "quality-engineering-lab-sut",
                    "status": "ok",
                    "endpoints": [
                        "/health/live",
                        "/health/ready",
                        "/.well-known/openid-configuration",
                        "/oauth/token",
                        "/oauth/revoke",
                        "/api/v1/auth/me",
                        "/api/v1/admin/audit",
                        "/api/v1/workspaces/{slug}/catalog",
                    ],
                },
            )
            return

        if path == "/health/live":
            self._send_json(HTTPStatus.OK, {"status": "live"})
            return

        if path == "/health/ready":
            self._handle_readiness()
            return

        if path == "/.well-known/openid-configuration":
            self._send_json(
                HTTPStatus.OK,
                {
                    "issuer": AUTH_ISSUER,
                    "token_endpoint": "/oauth/token",
                    "userinfo_endpoint": "/api/v1/auth/me",
                    "revocation_endpoint": "/oauth/revoke",
                    "grant_types_supported": [
                        "password",
                        "refresh_token",
                    ],
                },
            )
            return

        if path == "/api/v1/auth/me":
            self._handle_me()
            return

        if path == "/api/v1/admin/audit":
            self._handle_admin_audit()
            return

        catalog_match = CATALOG_PATH.fullmatch(path)
        if catalog_match:
            self._handle_catalog(catalog_match.group(1))
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            {
                "error": "not_found",
                "message": f"No route matches GET {path}.",
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/oauth/token":
            self._handle_token()
            return

        if path == "/oauth/revoke":
            self._handle_revoke()
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            {
                "error": "not_found",
                "message": f"No route matches POST {path}.",
            },
        )

    def _handle_readiness(self) -> None:
        checks: dict[str, dict[str, Any]] = {}

        for name, check in (
            ("postgres", _postgres_check),
            ("redis", _redis_check),
        ):
            try:
                checks[name] = check()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Readiness check failed for %s: %s", name, exc)
                checks[name] = {
                    "status": "error",
                    "error": type(exc).__name__,
                }

        ready = all(check["status"] == "ok" for check in checks.values())
        status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
        self._send_json(
            status,
            {
                "status": "ready" if ready else "degraded",
                "checks": checks,
            },
        )

    def _handle_catalog(self, slug: str) -> None:
        try:
            status, payload = _catalog_payload(slug)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Catalog query failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "database_unavailable",
                    "message": type(exc).__name__,
                },
            )
            return

        self._send_json(status, payload)

    def _handle_token(self) -> None:
        try:
            payload = self._read_request_payload()
        except (UnicodeDecodeError, ValueError) as exc:
            self._send_oauth_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                str(exc),
            )
            return

        grant_type = payload.get("grant_type")
        if grant_type == "password":
            username = payload.get("username")
            password = payload.get("password")
            if not isinstance(username, str) or not isinstance(password, str):
                self._send_oauth_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_request",
                    "username and password are required",
                )
                return
            user = _authenticate_password(username, password)
            if user is None:
                self._send_oauth_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_grant",
                    "username or password is invalid",
                )
                return
        elif grant_type == "refresh_token":
            refresh_token = payload.get("refresh_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                self._send_oauth_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_request",
                    "refresh_token is required",
                )
                return
            user_id = _consume_refresh_token(refresh_token)
            user = _find_user_by_id(user_id) if user_id is not None else None
            if user is None or user["status"] != "active":
                self._send_oauth_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_grant",
                    "refresh token is invalid, expired, or already used",
                )
                return
        else:
            self._send_oauth_error(
                HTTPStatus.BAD_REQUEST,
                "unsupported_grant_type",
                "supported grants are password and refresh_token",
            )
            return

        token_payload, _ = _token_response(user)
        access_token = str(token_payload["access_token"])
        self._send_json(
            HTTPStatus.OK,
            token_payload,
            headers={
                "Set-Cookie": (
                    f"qa_access_token={access_token}; Path=/; HttpOnly; "
                    f"SameSite=Lax; Max-Age={AUTH_ACCESS_TOKEN_TTL_SECONDS}"
                )
            },
        )

    def _handle_revoke(self) -> None:
        try:
            payload = self._read_request_payload()
        except (UnicodeDecodeError, ValueError) as exc:
            self._send_oauth_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                str(exc),
            )
            return

        token = payload.get("token")
        if isinstance(token, str) and token:
            _revoke_refresh_token(token)

        self._send_json(
            HTTPStatus.OK,
            {"revoked": True},
            headers={
                "Set-Cookie": (
                    "qa_access_token=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
                )
            },
        )

    def _handle_me(self) -> None:
        user = self._authenticated_user()
        if user is None:
            return
        self._send_json(HTTPStatus.OK, _user_payload(user))

    def _handle_admin_audit(self) -> None:
        user = self._authenticated_user()
        if user is None:
            return
        if user["role"] not in {"owner", "admin"}:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {
                    "error": "permission_denied",
                    "message": "The authenticated role cannot read the audit view.",
                },
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "workspace_slug": user["workspace_slug"],
                "role": user["role"],
                "events": ["workspace.created", "user.invited"],
            },
        )

    def _authenticated_user(self) -> dict[str, Any] | None:
        token = self._access_token()
        if token is None:
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "authentication_required",
                    "message": "Provide a Bearer token or access cookie.",
                },
            )
            return None

        try:
            claims = _decode_access_token(token, now=int(time.time()))
            user_id = int(claims["sub"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_token",
                    "message": "The access token is invalid or expired.",
                },
            )
            return None

        user = _find_user_by_id(user_id)
        if user is None or user["status"] != "active":
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_token",
                    "message": "The token user is missing or disabled.",
                },
            )
            return None
        return user

    def _access_token(self) -> str | None:
        authorization = self.headers.get("Authorization")
        if authorization is not None:
            scheme, _, credentials = authorization.partition(" ")
            if scheme.lower() != "bearer" or not credentials:
                return None
            return credentials

        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get("qa_access_token")
        return morsel.value if morsel is not None else None

    def _read_request_payload(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Content-Length must be an integer") from exc
        if content_length < 0:
            raise ValueError("Content-Length cannot be negative")

        raw_body = self.rfile.read(content_length) if content_length else b""
        if not raw_body:
            return {}

        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type == "application/x-www-form-urlencoded":
            fields = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
            return {name: values[-1] for name, values in fields.items()}
        if media_type == "application/json":
            payload = json.loads(raw_body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON request body must be an object")
            return payload
        raise ValueError(f"unsupported Content-Type: {media_type or '<missing>'}")

    def _send_oauth_error(
        self,
        status: HTTPStatus,
        error: str,
        description: str,
    ) -> None:
        self._send_json(
            status,
            {
                "error": error,
                "error_description": description,
            },
        )

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    """Start the HTTP server."""

    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), SutRequestHandler)
    LOGGER.info("SUT API listening on port %s", port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("SUT API interrupted")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
