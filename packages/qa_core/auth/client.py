"""OAuth2/OIDC-oriented authentication client with concurrent refresh control."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any, Literal, Self, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from qa_core.config.settings import Settings
from qa_core.contracts import TokenResponse
from qa_core.http import HttpClient

AuthMode = Literal["bearer", "cookie"]


class AuthenticationError(Exception):
    """Base class for authentication SDK failures."""


class AuthenticationRequired(AuthenticationError):
    """Raised when an operation needs a session that has not been established."""


class OAuthError(AuthenticationError):
    """Represent a structured OAuth2 error response."""

    def __init__(
        self,
        *,
        status_code: int,
        error: str,
        description: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.description = description
        message = f"OAuth2 request failed with HTTP {status_code}: {error}"
        if description:
            message = f"{message} ({description})"
        super().__init__(message)


class RefreshTokenInvalid(OAuthError):
    """Raised when a refresh token is expired, revoked, or already rotated."""


class OidcMetadata(BaseModel):
    """Subset of OpenID Connect discovery metadata used by the SDK."""

    model_config = ConfigDict(frozen=True)

    issuer: str = Field(min_length=1)
    token_endpoint: str = Field(min_length=1)
    userinfo_endpoint: str | None = None
    revocation_endpoint: str | None = None
    grant_types_supported: tuple[str, ...] = ()


class TokenSet(BaseModel):
    """Access and refresh tokens with an absolute expiry for local scheduling."""

    model_config = ConfigDict(frozen=True)

    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    token_type: str = Field(default="Bearer", min_length=1)
    expires_at: float = Field(gt=0)
    scope: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, now: float) -> Self:
        """Build a token set from an OAuth2 token response."""

        response = TokenResponse.model_validate(payload)

        return cls(
            access_token=response.access_token,
            refresh_token=response.refresh_token,
            token_type=response.token_type,
            expires_at=now + response.expires_in,
            scope=response.scope,
        )

    @property
    def authorization_header(self) -> str:
        """Return the HTTP Authorization header value."""

        return f"{self.token_type} {self.access_token}"

    def expires_within(self, seconds: float, *, now: float) -> bool:
        """Return whether the access token expires within the safety window."""

        return self.expires_at - now <= seconds


def decode_jwt_claims_unverified(token: str) -> dict[str, Any]:
    """Decode JWT claims for expiry and routing metadata without trusting them.

    JWT signature and issuer verification remain the authorization server's
    security boundary. Client-side tests only use this for scheduling and
    diagnostics.
    """

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("JWT must contain exactly three segments")

    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_segment + padding)
        payload = json.loads(decoded.decode("utf-8"))
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("JWT payload is not valid base64url JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("JWT payload must be a JSON object")
    return cast(dict[str, Any], payload)


def encode_hs256_jwt(claims: Mapping[str, Any], *, secret: str) -> str:
    """Sign an HS256 JWT for negative-path tests.

    Tests use this to craft expired, wrongly-issued, or forged tokens against
    the local SUT so those boundaries are deterministic. The secret here is the
    documented local development value, never a production credential.
    """

    def _segment(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _segment(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _segment(
        json.dumps(dict(claims), separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_payload}.{_segment(signature)}"


class AuthClient:
    """Manage token acquisition, refresh, and authenticated HTTP requests."""

    def __init__(
        self,
        http_client: HttpClient,
        *,
        mode: AuthMode = "bearer",
        token_path: str = "/oauth/token",
        revoke_path: str = "/oauth/revoke",
        discovery_path: str = "/.well-known/openid-configuration",
        refresh_skew_seconds: float = 30.0,
        time_source: Callable[[], float] = time.time,
    ) -> None:
        self._http = http_client
        self.mode = mode
        self._token_path = token_path
        self._revoke_path = revoke_path
        self._discovery_path = discovery_path
        self._refresh_skew_seconds = refresh_skew_seconds
        self._time_source = time_source
        self._tokens: TokenSet | None = None
        self._refresh_lock = threading.Lock()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        mode: AuthMode | None = None,
        http_client: HttpClient | None = None,
    ) -> Self:
        """Build an auth client from shared project settings."""

        return cls(
            http_client or HttpClient.from_settings(settings),
            mode=mode or settings.auth_mode,
            token_path=settings.auth_token_path,
            revoke_path=settings.auth_revoke_path,
            discovery_path=settings.auth_discovery_path,
            refresh_skew_seconds=settings.auth_refresh_skew_seconds,
        )

    @property
    def tokens(self) -> TokenSet | None:
        """Return the current token set without exposing mutable state."""

        return self._tokens

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""

        self._http.close()

    def discover(self) -> OidcMetadata:
        """Read OpenID Connect discovery metadata."""

        response = self._http.get(self._discovery_path)
        if response.status_code >= 400:
            raise self._oauth_error(response)
        try:
            return OidcMetadata.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise OAuthError(
                status_code=response.status_code,
                error="invalid_discovery_document",
                description=str(exc),
            ) from exc

    def login(self, username: str, password: str) -> TokenSet:
        """Acquire a token set with the password grant used by the local SUT."""

        self._http.clear_cookies()
        tokens = self._request_tokens(
            {
                "grant_type": "password",
                "username": username,
                "password": password,
                "scope": "openid profile",
            },
            refresh_grant=False,
        )
        self._tokens = tokens
        return tokens

    def refresh(self) -> TokenSet:
        """Explicitly rotate the refresh token and replace the access token."""

        return self._refresh_locked(force=True)

    def logout(self) -> None:
        """Revoke the current refresh token and clear local cookie state."""

        tokens = self._tokens
        if tokens is not None:
            response = self._http.post(
                self._revoke_path,
                data={"token": tokens.refresh_token},
            )
            if response.status_code >= 400:
                raise self._oauth_error(response)
        self._tokens = None
        self._http.clear_cookies()

    def request(
        self,
        method: str,
        url: str,
        *,
        refresh_on_401: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an authenticated request and recover once from an expired token."""

        normalized_method = method.upper()
        for attempt in range(2):
            access_token = self._ensure_access_token()
            request_kwargs = dict(kwargs)
            if self.mode == "bearer":
                headers = httpx.Headers(request_kwargs.pop("headers", None))
                headers["Authorization"] = f"Bearer {access_token}"
                request_kwargs["headers"] = headers

            response = self._http.request(normalized_method, url, **request_kwargs)
            if (
                response.status_code != 401
                or not refresh_on_401
                or attempt == 1
            ):
                return response

            response.close()
            self._refresh_locked(
                force=True,
                failed_access_token=access_token,
            )

        raise RuntimeError("Authenticated request loop exited without a response.")

    def get(
        self,
        url: str,
        *,
        refresh_on_401: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an authenticated GET request."""

        return self.request(
            "GET",
            url,
            refresh_on_401=refresh_on_401,
            **kwargs,
        )

    def post(
        self,
        url: str,
        *,
        refresh_on_401: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an authenticated POST request."""

        return self.request(
            "POST",
            url,
            refresh_on_401=refresh_on_401,
            **kwargs,
        )

    def _ensure_access_token(self) -> str:
        tokens = self._tokens
        if tokens is None:
            raise AuthenticationRequired("Call login() before authenticated requests.")
        if not tokens.expires_within(
            self._refresh_skew_seconds,
            now=self._time_source(),
        ):
            return tokens.access_token
        return self._refresh_locked(force=False).access_token

    def _refresh_locked(
        self,
        *,
        force: bool,
        failed_access_token: str | None = None,
    ) -> TokenSet:
        with self._refresh_lock:
            current = self._tokens
            if current is None:
                raise AuthenticationRequired("No refresh token is available.")
            if (
                failed_access_token is not None
                and current.access_token != failed_access_token
            ):
                return current
            if (
                failed_access_token is None
                and not force
                and not current.expires_within(
                    self._refresh_skew_seconds,
                    now=self._time_source(),
                )
            ):
                return current

            try:
                refreshed = self._request_tokens(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": current.refresh_token,
                    },
                    refresh_grant=True,
                )
            except OAuthError:
                self._tokens = None
                self._http.clear_cookies()
                raise

            self._tokens = refreshed
            return refreshed

    def _request_tokens(
        self,
        data: dict[str, str],
        *,
        refresh_grant: bool,
    ) -> TokenSet:
        response = self._http.post(
            self._token_path,
            data=data,
            headers={"Accept": "application/json"},
        )
        if response.status_code >= 400:
            raise self._oauth_error(response, refresh_grant=refresh_grant)

        try:
            payload = response.json()
        except ValueError as exc:
            raise OAuthError(
                status_code=response.status_code,
                error="invalid_token_response",
                description="response body is not JSON",
            ) from exc
        if not isinstance(payload, dict):
            raise OAuthError(
                status_code=response.status_code,
                error="invalid_token_response",
                description="response body must be a JSON object",
            )

        try:
            return TokenSet.from_payload(
                cast(dict[str, Any], payload),
                now=self._time_source(),
            )
        except ValueError as exc:
            raise OAuthError(
                status_code=response.status_code,
                error="invalid_token_response",
                description=str(exc),
            ) from exc

    @staticmethod
    def _oauth_error(
        response: httpx.Response,
        *,
        refresh_grant: bool = False,
    ) -> OAuthError:
        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if isinstance(payload, dict):
            raw_error = payload.get("error", "oauth_request_failed")
            raw_description = payload.get("error_description")
        else:
            raw_error = "oauth_request_failed"
            raw_description = None

        error = raw_error if isinstance(raw_error, str) else "oauth_request_failed"
        description = (
            raw_description if isinstance(raw_description, str) else None
        )
        exception_type = (
            RefreshTokenInvalid
            if refresh_grant and response.status_code in {400, 401}
            else OAuthError
        )
        return exception_type(
            status_code=response.status_code,
            error=error,
            description=description,
        )
