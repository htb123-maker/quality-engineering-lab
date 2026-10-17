"""Small local API with read-only business data and auth session state."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import os
import queue
import re
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import psycopg
import redis
from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel
from qa_core.contracts import (
    AdminAuditResponse,
    ApiError,
    CacheRefreshRequest,
    CatalogItem,
    CatalogItemCreate,
    CatalogItemStatusUpdate,
    CatalogResponse,
    CatalogWorkspace,
    ContractValidationError,
    FieldError,
    HealthCheck,
    HealthLiveResponse,
    JobAcceptedResponse,
    JobQueueStatsResponse,
    JobResponse,
    MemberCreate,
    MemberResponse,
    MemberRoleUpdate,
    MembersResponse,
    OAuthErrorResponse,
    OidcMetadataResponse,
    PermissionsResponse,
    ReadinessResponse,
    RevokeResponse,
    RootResponse,
    TokenResponse,
    UserResponse,
    ValidationErrorResponse,
    openapi_document,
    validate_contract,
)

ResponsePayload = BaseModel | dict[str, Any]

POSTGRES_DSN = os.getenv(
    "QA_POSTGRES_DSN",
    "postgresql://qa:qa@postgres:5432/qa",
)
POSTGRES_MAX_CONNECTIONS = max(
    1,
    int(os.getenv("QA_POSTGRES_MAX_CONNECTIONS", "16")),
)
POSTGRES_CONNECTION_TIMEOUT_SECONDS = max(
    0.1,
    float(os.getenv("QA_POSTGRES_CONNECTION_TIMEOUT_SECONDS", "2")),
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
CATALOG_ITEMS_PATH = re.compile(r"^/api/v1/workspaces/([^/]+)/catalog/items$")
CATALOG_ITEM_PATH = re.compile(
    r"^/api/v1/workspaces/([^/]+)/catalog/items/([0-9]+)$"
)
CACHE_REFRESH_PATH = re.compile(
    r"^/api/v1/workspaces/([^/]+)/catalog/cache/refresh$"
)
EVENTS_PATH = re.compile(r"^/api/v1/workspaces/([^/]+)/events$")
MEMBERS_PATH = re.compile(r"^/api/v1/workspaces/([^/]+)/members$")
MEMBER_PATH = re.compile(r"^/api/v1/workspaces/([^/]+)/members/([0-9]+)$")
PERMISSIONS_PATH = "/api/v1/auth/permissions"
JOB_PATH = re.compile(r"^/api/v1/jobs/([^/]+)$")
# Workspace slugs are the only user-supplied path segment that reaches the
# database, so they are validated before any query runs. Anything outside this
# alphabet (``..``, ``%2f``, uppercase, NUL) is rejected as a bad identifier
# instead of being handed to PostgreSQL as a lookup key.
WORKSPACE_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,58}[a-z0-9])?$")
ALLOWED_STATUS_TRANSITIONS = frozenset({("active", "archived")})
IDEMPOTENCY_TTL_SECONDS = int(os.getenv("QA_IDEMPOTENCY_TTL_SECONDS", "3600"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("QA_RATE_LIMIT_WRITE_MAX", "20"))
RATE_LIMIT_WINDOW_SECONDS = float(
    os.getenv("QA_RATE_LIMIT_WRITE_WINDOW_SECONDS", "60")
)
# The client-supplied ``X-QA-Client-Id`` header is easy to rotate, so the same
# requests are also counted against the authenticated principal. The principal
# bucket is deliberately roomier: it is a backstop against header rotation, not
# the primary pacing mechanism.
RATE_LIMIT_PRINCIPAL_MAX_REQUESTS = int(
    os.getenv("QA_RATE_LIMIT_PRINCIPAL_MAX", str(RATE_LIMIT_MAX_REQUESTS * 2))
)
# Both buckets live in Redis so the budget is shared by API replicas and can be
# cleared by the test-side namespace pool when a workspace is handed back.
RATE_LIMIT_CLIENT_PREFIX = "ratelimit:write:client:"
RATE_LIMIT_PRINCIPAL_PREFIX = "ratelimit:write:principal:"
AUTH_SIGNIN_FAILURE_MAX = int(os.getenv("QA_AUTH_SIGNIN_FAILURE_MAX", "10"))
AUTH_SIGNIN_FAILURE_WINDOW_SECONDS = float(
    os.getenv("QA_AUTH_SIGNIN_FAILURE_WINDOW_SECONDS", "60")
)
AUTH_SIGNIN_FAILURE_PREFIX = "auth:signin-failures:"
MAX_REQUEST_BYTES = int(os.getenv("QA_MAX_REQUEST_BYTES", "65536"))

# Capability registry: one place decides what a role may do, and every handler
# asks for a capability instead of comparing role strings. Roles are ordered by
# privilege, and ``owner`` is the only role that can hand out ``admin``.
ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "owner": frozenset(
        {
            "audit:read",
            "catalog:read",
            "catalog:refresh",
            "catalog:write",
            "events:read",
            "jobs:read",
            "members:read",
            "members:write",
        }
    ),
    "admin": frozenset(
        {
            "audit:read",
            "catalog:read",
            "catalog:refresh",
            "catalog:write",
            "events:read",
            "jobs:read",
            "members:read",
            "members:write",
        }
    ),
    "member": frozenset(
        {
            "catalog:read",
            "catalog:refresh",
            "catalog:write",
            "events:read",
            "jobs:read",
            "members:read",
        }
    ),
    "viewer": frozenset(
        {
            "catalog:read",
            "events:read",
            "jobs:read",
        }
    ),
}
ASSIGNABLE_ROLES = frozenset({"admin", "member", "viewer"})
ADMIN_ASSIGNABLE_ROLES = frozenset({"member", "viewer"})


def capabilities_for(role: str) -> list[str]:
    """Return the sorted capabilities of one role."""

    return sorted(ROLE_CAPABILITIES.get(role, frozenset()))


def has_capability(role: str, capability: str) -> bool:
    """Return whether one role carries one capability."""

    return capability in ROLE_CAPABILITIES.get(role, frozenset())

# Week 10 cache and queue configuration. The defaults keep the SUT friendly for
# manual exploration; tests tighten the TTLs through Compose environment values.
CATALOG_CACHE_PREFIX = "cache:catalog"
CACHE_STATS_PREFIX = "cache:stats"
CACHE_STATS_TTL_SECONDS = int(os.getenv("QA_CACHE_STATS_TTL_SECONDS", "3600"))
CATALOG_CACHE_TTL_SECONDS = int(os.getenv("QA_CATALOG_CACHE_TTL_SECONDS", "60"))
CATALOG_CACHE_NEGATIVE_TTL_SECONDS = int(
    os.getenv("QA_CATALOG_CACHE_NEGATIVE_TTL_SECONDS", "10")
)
JOB_QUEUE_KEY = "jobs:queue"
JOB_DELAYED_KEY = "jobs:delayed"
JOB_STATS_PREFIX = "jobs:stats:"
JOB_KEY_PREFIX = "job:"
JOB_TTL_SECONDS = int(os.getenv("QA_JOB_TTL_SECONDS", "900"))
JOB_WORKER_POLL_SECONDS = float(os.getenv("QA_JOB_WORKER_POLL_SECONDS", "0.25"))
JOB_WORKER_ENABLED = os.getenv("QA_JOB_WORKER_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
WS_SUBSCRIBER_QUEUE_SIZE = int(os.getenv("QA_WS_SUBSCRIBER_QUEUE_SIZE", "64"))
WS_POLL_SECONDS = float(os.getenv("QA_WS_POLL_SECONDS", "0.2"))
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WS_OPCODE_CONTINUATION = 0x0
WS_OPCODE_TEXT = 0x1
WS_OPCODE_CLOSE = 0x8
WS_OPCODE_PING = 0x9
WS_OPCODE_PONG = 0xA

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("sut-api")


class ConnectionBudgetExhausted(RuntimeError):
    """Raised when no PostgreSQL connection slot becomes available in time."""


@dataclass(frozen=True)
class ConnectionBudgetSnapshot:
    """Point-in-time usage of one bounded connection resource."""

    capacity: int
    active: int
    peak: int
    wait_seconds: float


class ConnectionBudget:
    """Bound concurrent database connections and expose high-water evidence."""

    def __init__(self, *, capacity: int, wait_seconds: float) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if wait_seconds <= 0:
            raise ValueError("wait_seconds must be positive")
        self._capacity = capacity
        self._wait_seconds = wait_seconds
        self._slots = threading.BoundedSemaphore(capacity)
        self._state_lock = threading.Lock()
        self._active = 0
        self._peak = 0

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Hold one slot for the duration of a database operation."""

        acquired = self._slots.acquire(timeout=self._wait_seconds)
        if not acquired:
            raise ConnectionBudgetExhausted(
                "PostgreSQL connection budget is exhausted"
            )
        with self._state_lock:
            self._active += 1
            self._peak = max(self._peak, self._active)
        try:
            yield
        finally:
            with self._state_lock:
                self._active -= 1
            self._slots.release()

    @property
    def snapshot(self) -> ConnectionBudgetSnapshot:
        """Return capacity, current usage, and the observed peak."""

        with self._state_lock:
            return ConnectionBudgetSnapshot(
                capacity=self._capacity,
                active=self._active,
                peak=self._peak,
                wait_seconds=self._wait_seconds,
            )


_POSTGRES_BUDGET = ConnectionBudget(
    capacity=POSTGRES_MAX_CONNECTIONS,
    wait_seconds=POSTGRES_CONNECTION_TIMEOUT_SECONDS,
)


@contextmanager
def _postgres_connection() -> Iterator[Connection[dict[str, Any]]]:
    """Open one budgeted PostgreSQL connection and close it on exit."""

    with _POSTGRES_BUDGET.slot():
        raw_connection = psycopg.connect(POSTGRES_DSN, connect_timeout=2)
        connection = cast(Connection[dict[str, Any]], raw_connection)
        with connection:
            yield connection


def _postgres_check() -> dict[str, Any]:
    with _postgres_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT current_database() AS database, current_user AS user"
            )
            row = cursor.fetchone()

    return {
        "status": "ok",
        "database": row["database"] if row else None,
        "user": row["user"] if row else None,
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
        _close_quietly(client)

    return {"status": "ok", "ping": bool(pong)}


def _redis_client() -> redis.Redis:
    """Open one short-lived Redis connection.

    Every helper closes its own client so a request thread never shares a
    socket with the background worker.
    """

    return redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def _close_quietly(client: Any) -> None:
    """Close a Redis client without masking the result of the operation.

    A connection that is already broken raises on ``close`` too; that must not
    turn a clean "Redis is unavailable, degrade" path into a 500.
    """

    try:
        client.close()
    except (redis.RedisError, OSError):
        pass


def _find_user_by_email(email: str) -> dict[str, Any] | None:
    with _postgres_connection() as connection:
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
    with _postgres_connection() as connection:
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
    client = _redis_client()
    try:
        client.setex(
            _refresh_key(token),
            AUTH_REFRESH_TOKEN_TTL_SECONDS,
            str(user["id"]),
        )
    finally:
        _close_quietly(client)
    return token


def _consume_refresh_token(token: str) -> int | None:
    client = _redis_client()
    try:
        user_id = client.getdel(_refresh_key(token))
    finally:
        _close_quietly(client)

    if user_id is None:
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


def _revoke_refresh_token(token: str) -> None:
    client = _redis_client()
    try:
        client.delete(_refresh_key(token))
    finally:
        _close_quietly(client)


def _authenticate_password(username: str, password: str) -> dict[str, Any] | None:
    if not hmac.compare_digest(password, AUTH_TEST_PASSWORD):
        return None
    user = _find_user_by_email(username)
    if user is None or user["status"] != "active":
        return None
    return user


def _token_response(user: dict[str, Any]) -> tuple[TokenResponse, str]:
    now = int(time.time())
    access_token = _issue_access_token(user, now=now)
    refresh_token = _create_refresh_token(user)
    return (
        TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=AUTH_ACCESS_TOKEN_TTL_SECONDS,
            scope="openid profile",
        ),
        refresh_token,
    )


def _user_payload(user: dict[str, Any]) -> UserResponse:
    return UserResponse(
        id=user["id"],
        workspace_id=user["workspace_id"],
        workspace_slug=user["workspace_slug"],
        email=user["email"],
        display_name=user["display_name"],
        role=user["role"],
        status=user["status"],
    )


def _catalog_payload(slug: str) -> tuple[HTTPStatus, CatalogResponse | ApiError]:
    with _postgres_connection() as connection:
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
                return HTTPStatus.NOT_FOUND, ApiError(
                    error="workspace_not_found",
                    message=f"Workspace '{slug}' was not found.",
                )

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

    return HTTPStatus.OK, CatalogResponse(
        workspace=CatalogWorkspace(
            slug=workspace["slug"],
            name=workspace["name"],
        ),
        items=[CatalogItem.model_validate(item) for item in items],
        count=len(items),
    )


class RequestBodyError(Exception):
    """A request body problem that maps to one HTTP status and error code."""

    def __init__(self, status: HTTPStatus, error: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message


@dataclass(frozen=True)
class RateLimitSnapshot:
    """The state of one fixed-window bucket after a request was counted."""

    scope: str
    limit: int
    remaining: int
    reset_after: float
    allowed: bool = True

    @property
    def limited(self) -> bool:
        """Return whether this bucket refused the request.

        ``remaining == 0`` on its own is not a refusal: the request that spends
        the last unit of budget is still allowed, so the two facts are tracked
        separately.
        """

        return not self.allowed

    @property
    def utilization(self) -> float:
        """Return how full the bucket is, used to pick the binding one."""

        if self.limit <= 0:
            return 0.0
        return (self.limit - self.remaining) / self.limit


class RedisFixedWindowBudget:
    """Count requests per key inside a fixed Redis window.

    Redis, not process memory, owns the counter: the budget therefore survives
    a restart and is shared by every API replica, and the test suite can clear
    one principal's counter when it hands a namespace back to the pool.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        scope: str,
        prefix: str,
        client_factory: Any = None,
    ) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._scope = scope
        self._prefix = prefix
        self._client_factory = client_factory or _redis_client

    @property
    def prefix(self) -> str:
        """Return the Redis key prefix this bucket owns."""

        return self._prefix

    @property
    def window_seconds(self) -> int:
        """Return the window as whole seconds, which is what Redis stores."""

        return max(1, math.ceil(self._window_seconds))

    def consume(self, key: str) -> RateLimitSnapshot:
        """Count one request for ``key`` and report the resulting state.

        A Redis outage fails open: the local SUT stays writable and logs the
        degradation instead of turning a cache outage into an API outage.
        """

        if self._limit <= 0:
            return RateLimitSnapshot(
                scope=self._scope,
                limit=0,
                remaining=0,
                reset_after=0.0,
            )

        redis_key = f"{self._prefix}{key}"
        client = self._client_factory()
        try:
            counted = int(client.incr(redis_key))
            if counted == 1:
                client.expire(redis_key, self.window_seconds)
            ttl = client.ttl(redis_key)
            reset_after = float(ttl) if int(ttl) > 0 else float(self.window_seconds)
        except (redis.RedisError, TypeError, ValueError) as exc:
            LOGGER.warning("Rate-limit bucket %s unavailable: %s", self._scope, exc)
            return RateLimitSnapshot(
                scope=self._scope,
                limit=self._limit,
                remaining=self._limit,
                reset_after=0.0,
            )
        finally:
            _close_quietly(client)

        if counted > self._limit:
            return RateLimitSnapshot(
                scope=self._scope,
                limit=self._limit,
                remaining=0,
                reset_after=reset_after,
                allowed=False,
            )
        return RateLimitSnapshot(
            scope=self._scope,
            limit=self._limit,
            remaining=self._limit - counted,
            reset_after=reset_after,
        )

    def clear(self, key: str) -> None:
        """Drop one key's counter, used when a test releases a namespace."""

        client = self._client_factory()
        try:
            client.delete(f"{self._prefix}{key}")
        except redis.RedisError as exc:
            LOGGER.warning("Rate-limit bucket %s reset failed: %s", self._scope, exc)
        finally:
            _close_quietly(client)


def client_budget_key(client_id: str) -> str:
    """Hash the caller-controlled client id before it becomes a Redis key."""

    return hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:32]


def principal_budget_key(user_id: int) -> str:
    """Return the bucket key for one authenticated principal."""

    return f"user:{user_id}"


_CLIENT_BUDGET = RedisFixedWindowBudget(
    limit=RATE_LIMIT_MAX_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    scope="client",
    prefix=RATE_LIMIT_CLIENT_PREFIX,
)
_PRINCIPAL_BUDGET = RedisFixedWindowBudget(
    limit=RATE_LIMIT_PRINCIPAL_MAX_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    scope="principal",
    prefix=RATE_LIMIT_PRINCIPAL_PREFIX,
)


def _consume_write_budget(
    client_id: str,
    user_id: int,
) -> RateLimitSnapshot:
    """Count one write against both buckets and report the binding one.

    The client bucket is checked first because it is the primary pacer. When it
    still has room the principal bucket decides the reported numbers, so a test
    client that rotates ``X-QA-Client-Id`` still sees the budget shrink.
    """

    client_state = _CLIENT_BUDGET.consume(client_budget_key(client_id))
    if client_state.limited:
        return client_state
    principal_state = _PRINCIPAL_BUDGET.consume(principal_budget_key(user_id))
    if principal_state.limited:
        return principal_state
    if principal_state.utilization > client_state.utilization:
        return principal_state
    return client_state


def _rate_limit_headers(state: RateLimitSnapshot) -> dict[str, str]:
    """Return the budget headers echoed with a limited response."""

    headers = {
        "X-RateLimit-Limit": str(state.limit),
        "X-RateLimit-Remaining": str(state.remaining),
        "X-RateLimit-Reset": str(max(1, math.ceil(state.reset_after))),
        "X-RateLimit-Scope": state.scope,
    }
    if state.limited:
        headers["Retry-After"] = str(max(1, math.ceil(state.reset_after)))
    return headers


def _signin_failure_key(client_id: str, email: str) -> str:
    digest = hashlib.sha256(f"{client_id}|{email.lower()}".encode()).hexdigest()
    return f"{AUTH_SIGNIN_FAILURE_PREFIX}{digest[:32]}"


def _signin_retry_after(key: str) -> float | None:
    """Return seconds left before a locked account may retry, else None.

    Redis failures fail open: the local SUT must stay usable when the cache is
    down, and the lockout protects convenience, not production data.
    """

    if AUTH_SIGNIN_FAILURE_MAX <= 0:
        return None
    client = _redis_client()
    try:
        failures = client.get(key)
        if failures is None or int(failures) < AUTH_SIGNIN_FAILURE_MAX:
            return None
        ttl = client.ttl(key)
    except (redis.RedisError, TypeError, ValueError) as exc:
        LOGGER.warning("Sign-in throttle read failed: %s", exc)
        return None
    finally:
        _close_quietly(client)
    return float(ttl) if ttl and ttl > 0 else AUTH_SIGNIN_FAILURE_WINDOW_SECONDS


def _record_signin_failure(key: str) -> None:
    """Count one failed password grant inside the throttle window."""

    if AUTH_SIGNIN_FAILURE_MAX <= 0:
        return
    window = max(1, math.ceil(AUTH_SIGNIN_FAILURE_WINDOW_SECONDS))
    client = _redis_client()
    try:
        failures = client.incr(key)
        if int(failures) == 1:
            client.expire(key, window)
    except (redis.RedisError, TypeError, ValueError) as exc:
        LOGGER.warning("Sign-in throttle write failed: %s", exc)
    finally:
        _close_quietly(client)


def _clear_signin_failures(key: str) -> None:
    """Drop the failure counter after a successful authentication."""

    client = _redis_client()
    try:
        client.delete(key)
    except redis.RedisError as exc:
        LOGGER.warning("Sign-in throttle reset failed: %s", exc)
    finally:
        _close_quietly(client)


def _idempotency_store_key(workspace_id: int, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"idem:{workspace_id}:{digest}"


def _body_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_idempotent_response(store_key: str) -> dict[str, Any] | None:
    client = _redis_client()
    try:
        raw = client.get(store_key)
    finally:
        _close_quietly(client)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _store_idempotent_response(
    store_key: str,
    *,
    fingerprint: str,
    status_code: int,
    payload: dict[str, Any],
) -> None:
    client = _redis_client()
    try:
        client.setex(
            store_key,
            IDEMPOTENCY_TTL_SECONDS,
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "status_code": status_code,
                    "payload": payload,
                },
                sort_keys=True,
            ),
        )
    finally:
        _close_quietly(client)


def _workspace_by_slug(slug: str) -> dict[str, Any] | None:
    with _postgres_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT id, slug, name FROM workspaces WHERE slug = %s",
                (slug,),
            )
            return cursor.fetchone()


def _catalog_item_by_id(workspace_id: int, item_id: int) -> dict[str, Any] | None:
    with _postgres_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, sku, name, price_cents, status
                FROM catalog_items
                WHERE workspace_id = %s AND id = %s
                """,
                (workspace_id, item_id),
            )
            return cursor.fetchone()


def _member_payload(row: dict[str, Any]) -> MemberResponse:
    """Convert one ``users`` row into the members API representation."""

    return MemberResponse(
        id=int(row["id"]),
        workspace_id=int(row["workspace_id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"]),
        role=str(row["role"]),
        status=str(row["status"]),
    )


def _workspace_members(workspace_id: int) -> list[dict[str, Any]]:
    """Return every member of one workspace, oldest first."""

    with _postgres_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, workspace_id, email, display_name, role, status
                FROM users
                WHERE workspace_id = %s
                ORDER BY id
                """,
                (workspace_id,),
            )
            return list(cursor.fetchall())


def _workspace_member(workspace_id: int, user_id: int) -> dict[str, Any] | None:
    """Return one member row, scoped to its workspace so ids cannot cross."""

    with _postgres_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, workspace_id, email, display_name, role, status
                FROM users
                WHERE workspace_id = %s AND id = %s
                """,
                (workspace_id, user_id),
            )
            return cursor.fetchone()


def _insert_workspace_member(
    workspace_id: int,
    request: MemberCreate,
) -> MemberResponse:
    """Invite one member and return the stored row."""

    with _postgres_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO users
                    (workspace_id, email, display_name, role, status)
                VALUES (%s, %s, %s, %s, 'active')
                RETURNING id, workspace_id, email, display_name, role, status
                """,
                (
                    workspace_id,
                    request.email,
                    request.display_name,
                    request.role,
                ),
            )
            row = cursor.fetchone()

    if row is None:
        raise RuntimeError("member insert returned no row")
    return _member_payload(row)


def _update_member_role(
    workspace_id: int,
    user_id: int,
    role: str,
) -> MemberResponse | None:
    """Change one member's role inside its workspace."""

    with _postgres_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                UPDATE users
                SET role = %s
                WHERE workspace_id = %s AND id = %s
                RETURNING id, workspace_id, email, display_name, role, status
                """,
                (role, workspace_id, user_id),
            )
            row = cursor.fetchone()

    return None if row is None else _member_payload(row)


def _delete_workspace_member(workspace_id: int, user_id: int) -> bool:
    """Delete one member row; the workspace itself is untouched."""

    with _postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM users WHERE workspace_id = %s AND id = %s",
                (workspace_id, user_id),
            )
            return cursor.rowcount == 1


def _create_catalog_item(
    workspace_id: int,
    request: CatalogItemCreate,
) -> CatalogItem:
    with _postgres_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO catalog_items (workspace_id, sku, name, price_cents, status)
                VALUES (%s, %s, %s, %s, 'active')
                RETURNING id, sku, name, price_cents, status
                """,
                (
                    workspace_id,
                    request.sku,
                    request.name,
                    request.price_cents,
                ),
            )
            row = cursor.fetchone()

    if row is None:
        raise RuntimeError("catalog item insert returned no row")
    return CatalogItem.model_validate(row)


def _update_catalog_item_status(
    workspace_id: int,
    item_id: int,
    status: str,
) -> CatalogItem | None:
    with _postgres_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                UPDATE catalog_items
                SET status = %s
                WHERE workspace_id = %s AND id = %s
                RETURNING id, sku, name, price_cents, status
                """,
                (status, workspace_id, item_id),
            )
            row = cursor.fetchone()

    return CatalogItem.model_validate(row) if row is not None else None


def _delete_catalog_item(workspace_id: int, item_id: int) -> bool:
    with _postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM catalog_items WHERE workspace_id = %s AND id = %s",
                (workspace_id, item_id),
            )
            return cursor.rowcount > 0


def _validation_error_payload(exc: ContractValidationError) -> ValidationErrorResponse:
    return ValidationErrorResponse(
        error="validation_failed",
        message=f"Request does not satisfy {exc.model_name}.",
        fields=[
            FieldError(
                field=violation.path,
                message=violation.message,
                type=violation.error_type,
            )
            for violation in exc.violations
        ],
    )


def catalog_cache_key(slug: str) -> str:
    """Return the Redis key that caches one workspace catalog."""

    return f"{CATALOG_CACHE_PREFIX}:{slug}"


def catalog_absent_cache_key(slug: str) -> str:
    """Return the Redis key that caches the "workspace not found" answer."""

    return f"{CATALOG_CACHE_PREFIX}:{slug}:absent"


def cache_stats_key(slug: str, name: str) -> str:
    """Return the Redis key that counts one cache outcome for a workspace."""

    return f"{CACHE_STATS_PREFIX}:{slug}:{name}"


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp used by job and event records."""

    return datetime.now(UTC).isoformat(timespec="seconds")


def _record_cache_stat(
    client: redis.Redis,
    slug: str,
    name: str,
    amount: int = 1,
) -> None:
    """Count one cache outcome; the counter expires so a test run leaks nothing."""

    key = cache_stats_key(slug, name)
    with client.pipeline() as pipe:
        pipe.incrby(key, amount)
        pipe.expire(key, CACHE_STATS_TTL_SECONDS)
        pipe.execute()


def _decode_cached_json(raw: bytes | str | None) -> dict[str, Any] | None:
    """Return a cached JSON object, or ``None`` when the entry is unusable."""

    if raw is None:
        return None
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _store_catalog_cache(
    slug: str,
    payload: CatalogResponse,
    *,
    ttl_seconds: int | None = None,
) -> int:
    """Write a catalog payload into Redis and drop a stale negative entry."""

    resolved_ttl = int(ttl_seconds or CATALOG_CACHE_TTL_SECONDS)
    body = json.dumps(payload.model_dump(mode="json"), sort_keys=True)
    client = _redis_client()
    try:
        client.setex(catalog_cache_key(slug), resolved_ttl, body)
        client.delete(catalog_absent_cache_key(slug))
    finally:
        _close_quietly(client)
    return resolved_ttl


def _invalidate_catalog_cache(slug: str) -> int:
    """Drop the cached catalog so the next read observes the write."""

    client = _redis_client()
    try:
        removed = int(client.delete(catalog_cache_key(slug)))
        _record_cache_stat(client, slug, "invalidations", removed)
        return removed
    finally:
        _close_quietly(client)


def _catalog_cache_aside(
    slug: str,
) -> tuple[HTTPStatus, CatalogResponse | ApiError, dict[str, str]]:
    """Serve the catalog from Redis, falling back to PostgreSQL on a miss.

    A miss stores the answer with a TTL: a positive entry for a real catalog and
    a short negative entry for an unknown workspace, which is what keeps a
    repeated request for a missing slug from reaching the database every time.
    """

    client = _redis_client()
    try:
        hit_key = catalog_cache_key(slug)
        cached = _decode_cached_json(client.get(hit_key))
        if cached is not None:
            _record_cache_stat(client, slug, "hit")
            return HTTPStatus.OK, CatalogResponse.model_validate(cached), {
                "X-Cache": "HIT",
                "X-Cache-TTL": str(int(client.ttl(hit_key))),
            }

        absent_key = catalog_absent_cache_key(slug)
        cached_absent = _decode_cached_json(client.get(absent_key))
        if cached_absent is not None:
            _record_cache_stat(client, slug, "hit_negative")
            return HTTPStatus.NOT_FOUND, ApiError.model_validate(cached_absent), {
                "X-Cache": "HIT-NEGATIVE",
                "X-Cache-TTL": str(int(client.ttl(absent_key))),
            }

        _record_cache_stat(client, slug, "miss")
        _record_cache_stat(client, slug, "db_reads")
        status, payload = _catalog_payload(slug)
        body = json.dumps(payload.model_dump(mode="json"), sort_keys=True)
        if status == HTTPStatus.OK:
            client.setex(hit_key, CATALOG_CACHE_TTL_SECONDS, body)
            written_ttl = CATALOG_CACHE_TTL_SECONDS
        else:
            client.setex(absent_key, CATALOG_CACHE_NEGATIVE_TTL_SECONDS, body)
            written_ttl = CATALOG_CACHE_NEGATIVE_TTL_SECONDS
        return status, payload, {
            "X-Cache": "MISS",
            "X-Cache-TTL": str(written_ttl),
        }
    finally:
        _close_quietly(client)


def _catalog_with_cache(
    slug: str,
) -> tuple[HTTPStatus, CatalogResponse | ApiError, dict[str, str]]:
    """Read the catalog through the cache, degrading to PostgreSQL when it fails."""

    try:
        return _catalog_cache_aside(slug)
    except redis.RedisError as exc:
        LOGGER.warning("Catalog cache unavailable, reading PostgreSQL: %s", exc)
        status, payload = _catalog_payload(slug)
        return status, payload, {"X-Cache": "BYPASS", "X-Cache-TTL": "-1"}


class EventBroker:
    """Fan workspace events out to WebSocket subscribers without blocking writers.

    Subscribers get a bounded queue, so one client that stops reading loses the
    oldest events instead of stalling the request thread that produced them.
    """

    def __init__(self, *, queue_size: int = WS_SUBSCRIBER_QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[queue.Queue[dict[str, Any]]]] = {}
        self._sequences: dict[str, int] = {}
        self._dropped = 0

    @property
    def subscriber_count(self) -> int:
        """Return how many subscribers are attached across all workspaces."""

        with self._lock:
            return sum(len(entries) for entries in self._subscribers.values())

    @property
    def dropped_events(self) -> int:
        """Return how many events were dropped for subscribers that stopped reading."""

        with self._lock:
            return self._dropped

    def subscribe(self, slug: str) -> queue.Queue[dict[str, Any]]:
        """Attach one bounded queue to a workspace event stream."""

        channel: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            self._subscribers.setdefault(slug, set()).add(channel)
        return channel

    def unsubscribe(self, slug: str, channel: queue.Queue[dict[str, Any]]) -> None:
        """Detach a queue; an already detached queue is ignored."""

        with self._lock:
            entries = self._subscribers.get(slug)
            if entries is None:
                return
            entries.discard(channel)
            if not entries:
                self._subscribers.pop(slug, None)

    def publish(
        self,
        slug: str,
        event_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Number one event and hand it to every current subscriber."""

        with self._lock:
            sequence = self._sequences.get(slug, 0) + 1
            self._sequences[slug] = sequence
            event = {
                "type": event_type,
                "workspace": slug,
                "sequence": sequence,
                "occurred_at": time.time(),
                "data": data,
            }
            for channel in list(self._subscribers.get(slug, ())):
                try:
                    channel.put_nowait(event)
                except queue.Full:
                    self._dropped += 1
                    LOGGER.warning(
                        "Dropped %s for a subscriber that stopped reading %s",
                        event_type,
                        slug,
                    )
        return event


EVENT_BROKER = EventBroker()


def job_key(job_id: str) -> str:
    """Return the Redis key that stores one job record."""

    return f"{JOB_KEY_PREFIX}{job_id}"


def _save_job(record: dict[str, Any]) -> None:
    """Persist one job record with a TTL so finished jobs do not pile up."""

    client = _redis_client()
    try:
        client.setex(
            job_key(str(record["job_id"])),
            JOB_TTL_SECONDS,
            json.dumps(record, sort_keys=True),
        )
    finally:
        _close_quietly(client)


def _load_job(job_id: str) -> dict[str, Any] | None:
    """Return one job record, or ``None`` when it expired or never existed."""

    client = _redis_client()
    try:
        raw = client.get(job_key(job_id))
    finally:
        _close_quietly(client)
    return _decode_cached_json(raw)


def _update_job(job_id: str, **changes: Any) -> dict[str, Any] | None:
    """Patch one job record in place and return the stored record."""

    record = _load_job(job_id)
    if record is None:
        return None
    record.update(changes)
    _save_job(record)
    return record


def _job_response(record: dict[str, Any]) -> JobResponse:
    """Project the stored record onto the documented response contract."""

    fields = (
        "job_id",
        "type",
        "workspace_slug",
        "status",
        "queued_at",
        "started_at",
        "finished_at",
        "result",
        "error",
    )
    return JobResponse.model_validate({name: record.get(name) for name in fields})


def _enqueue_job(
    *,
    job_type: str,
    workspace_slug: str,
    payload: dict[str, Any],
    delay_seconds: float = 0.0,
) -> dict[str, Any]:
    """Store a queued job and put it on the immediate or delayed queue."""

    job_id = uuid4().hex
    record: dict[str, Any] = {
        "job_id": job_id,
        "type": job_type,
        "workspace_slug": workspace_slug,
        "status": "queued",
        "queued_at": _utc_now(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
        "payload": payload,
    }
    _save_job(record)
    client = _redis_client()
    try:
        if delay_seconds > 0:
            client.zadd(JOB_DELAYED_KEY, {job_id: time.time() + delay_seconds})
        else:
            client.lpush(JOB_QUEUE_KEY, job_id)
    finally:
        _close_quietly(client)
    return record


def _bump_job_counter(name: str) -> None:
    """Count one finished job outcome."""

    client = _redis_client()
    try:
        client.incr(f"{JOB_STATS_PREFIX}{name}")
    finally:
        _close_quietly(client)


def _job_queue_stats() -> JobQueueStatsResponse:
    """Read queue depth and worker counters."""

    client = _redis_client()
    try:
        return JobQueueStatsResponse(
            queued=int(client.llen(JOB_QUEUE_KEY)),
            delayed=int(client.zcard(JOB_DELAYED_KEY)),
            processed=int(client.get(f"{JOB_STATS_PREFIX}processed") or 0),
            failed=int(client.get(f"{JOB_STATS_PREFIX}failed") or 0),
            worker_enabled=JOB_WORKER_ENABLED,
        )
    finally:
        _close_quietly(client)


class JobWorker(threading.Thread):
    """Run queued jobs in a daemon thread next to the API process.

    One process owns both roles here, which keeps the Compose stack small while
    still moving the work out of the request that asked for it: the caller gets
    a job id, and the cache is only warm once the worker has run.
    """

    def __init__(
        self,
        broker: EventBroker,
        *,
        poll_seconds: float = JOB_WORKER_POLL_SECONDS,
    ) -> None:
        super().__init__(name="sut-job-worker", daemon=True)
        self._broker = broker
        self._poll_seconds = poll_seconds
        self._stop = threading.Event()

    def stop(self) -> None:
        """Ask the worker loop to exit after the current job."""

        self._stop.set()

    def run(self) -> None:
        LOGGER.info("Job worker started")
        while not self._stop.is_set():
            try:
                self._promote_delayed_jobs()
                job_id = self._pop_job()
                if job_id is None:
                    continue
                self._process(job_id)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Job worker loop failed")
                self._stop.wait(self._poll_seconds)
        LOGGER.info("Job worker stopped")

    def _pop_job(self) -> str | None:
        """Block briefly for the next job id."""

        client = _redis_client()
        try:
            item = client.brpop(JOB_QUEUE_KEY, timeout=self._poll_seconds)
        finally:
            _close_quietly(client)
        if item is None:
            return None
        _, raw = item
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    def _promote_delayed_jobs(self) -> None:
        """Move delayed jobs whose not-before time has passed onto the queue."""

        client = _redis_client()
        try:
            due = client.zrangebyscore(JOB_DELAYED_KEY, 0, time.time())
            for raw_id in due:
                job_id = str(raw_id)
                if client.zrem(JOB_DELAYED_KEY, job_id):
                    client.lpush(JOB_QUEUE_KEY, job_id)
        finally:
            _close_quietly(client)

    def _process(self, job_id: str) -> None:
        """Run one job and record its outcome."""

        record = _load_job(job_id)
        if record is None:
            LOGGER.warning("Ignoring job %s because its record expired", job_id)
            return
        slug = str(record.get("workspace_slug", ""))
        _update_job(job_id, status="running", started_at=_utc_now())
        try:
            result = self._dispatch(record)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Job %s failed: %s", job_id, exc)
            _update_job(
                job_id,
                status="failed",
                finished_at=_utc_now(),
                error=f"{type(exc).__name__}: {exc}",
            )
            _bump_job_counter("failed")
            self._broker.publish(
                slug,
                "job.failed",
                {"job_id": job_id, "type": record.get("type"), "error": str(exc)},
            )
            return

        _update_job(job_id, status="succeeded", finished_at=_utc_now(), result=result)
        _bump_job_counter("processed")
        self._broker.publish(
            slug,
            "job.succeeded",
            {"job_id": job_id, "type": record.get("type"), "result": result},
        )

    def _dispatch(self, record: dict[str, Any]) -> dict[str, Any]:
        """Run the job handler that matches the job type."""

        job_type = record.get("type")
        if job_type == "catalog.cache_refresh":
            return self._refresh_catalog_cache(record)
        raise ValueError(f"unsupported job type: {job_type}")

    def _refresh_catalog_cache(self, record: dict[str, Any]) -> dict[str, Any]:
        """Read PostgreSQL and warm the cache the next read will hit."""

        slug = str(record["workspace_slug"])
        payload = record.get("payload")
        requested_ttl = None
        if isinstance(payload, dict):
            requested_ttl = payload.get("ttl_seconds")
        status, result = _catalog_payload(slug)
        if status != HTTPStatus.OK or not isinstance(result, CatalogResponse):
            raise ValueError(f"workspace_not_found: {slug}")
        ttl_seconds = _store_catalog_cache(
            slug,
            result,
            ttl_seconds=int(requested_ttl) if requested_ttl else None,
        )
        return {
            "workspace_slug": slug,
            "items": result.count,
            "ttl_seconds": ttl_seconds,
        }


def _append_ws_length(header: bytearray, length: int) -> None:
    """Append the payload length of a WebSocket frame, masked or not."""

    if length < 126:
        header.append(length)
    elif length < 65_536:
        header.append(126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(127)
        header.extend(length.to_bytes(8, "big"))


def encode_ws_frame(payload: bytes, *, opcode: int = WS_OPCODE_TEXT) -> bytes:
    """Encode one unmasked server-to-client WebSocket frame."""

    header = bytearray([0x80 | opcode])
    _append_ws_length(header, len(payload))
    return bytes(header) + payload


def encode_ws_text(payload: str) -> bytes:
    """Encode one JSON text frame."""

    return encode_ws_frame(payload.encode("utf-8"))


def read_ws_frame(rfile: Any) -> tuple[int, bytes] | None:
    """Read one client frame; return ``None`` when the stream ended."""

    header = rfile.read(2)
    if not header or len(header) < 2:
        return None
    opcode = header[0] & 0x0F
    masked = bool(header[1] & 0x80)
    length = header[1] & 0x7F
    if length == 126:
        extended = rfile.read(2)
        if not extended or len(extended) < 2:
            return None
        length = int.from_bytes(extended, "big")
    elif length == 127:
        extended = rfile.read(8)
        if not extended or len(extended) < 8:
            return None
        length = int.from_bytes(extended, "big")

    mask = b""
    if masked:
        mask = rfile.read(4)
        if not mask or len(mask) < 4:
            return None
    payload = rfile.read(length) if length else b""
    if payload is None or len(payload) < length:
        return None
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


def websocket_accept(key: str) -> str:
    """Return the Sec-WebSocket-Accept value for one client key."""

    digest = hashlib.sha1((key + WS_GUID).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


class SutRequestHandler(BaseHTTPRequestHandler):
    """Serve health, read-only catalog, and local authentication endpoints."""

    server_version = "QualityLabSut/0.1"

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/":
            self._send_json(
                HTTPStatus.OK,
                RootResponse(
                    service="quality-engineering-lab-sut",
                    status="ok",
                    endpoints=[
                        "/openapi.json",
                        "/health/live",
                        "/health/ready",
                        "/.well-known/openid-configuration",
                        "/oauth/token",
                        "/oauth/revoke",
                        "/api/v1/auth/me",
                        "/api/v1/auth/permissions",
                        "/api/v1/admin/audit",
                        "/api/v1/workspaces/{slug}/catalog",
                        "/api/v1/workspaces/{slug}/catalog/items",
                        "/api/v1/workspaces/{slug}/catalog/items/{item_id}",
                        "/api/v1/workspaces/{slug}/catalog/cache/refresh",
                        "/api/v1/workspaces/{slug}/members",
                        "/api/v1/workspaces/{slug}/members/{user_id}",
                        "/api/v1/workspaces/{slug}/events",
                        "/api/v1/jobs",
                        "/api/v1/jobs/{job_id}",
                    ],
                ),
            )
            return

        if path == "/openapi.json":
            self._send_json(HTTPStatus.OK, openapi_document())
            return

        if path == "/health/live":
            self._send_json(HTTPStatus.OK, HealthLiveResponse(status="live"))
            return

        if path == "/health/ready":
            self._handle_readiness()
            return

        if path == "/.well-known/openid-configuration":
            self._send_json(
                HTTPStatus.OK,
                OidcMetadataResponse(
                    issuer=AUTH_ISSUER,
                    token_endpoint="/oauth/token",
                    userinfo_endpoint="/api/v1/auth/me",
                    revocation_endpoint="/oauth/revoke",
                    grant_types_supported=[
                        "password",
                        "refresh_token",
                    ],
                ),
            )
            return

        if path == "/api/v1/auth/me":
            self._handle_me()
            return

        if path == "/api/v1/admin/audit":
            self._handle_admin_audit()
            return

        if path == PERMISSIONS_PATH:
            self._handle_permissions()
            return

        if path == "/api/v1/jobs":
            self._handle_job_queue_stats()
            return

        members_match = MEMBERS_PATH.fullmatch(path)
        if members_match:
            self._handle_members_list(members_match.group(1))
            return

        events_match = EVENTS_PATH.fullmatch(path)
        if events_match:
            self._handle_events(events_match.group(1))
            return

        job_match = JOB_PATH.fullmatch(path)
        if job_match:
            self._handle_job(job_match.group(1))
            return

        item_match = CATALOG_ITEM_PATH.fullmatch(path)
        if item_match:
            self._handle_catalog_item_read(
                item_match.group(1),
                int(item_match.group(2)),
            )
            return

        catalog_match = CATALOG_PATH.fullmatch(path)
        if catalog_match:
            self._handle_catalog(catalog_match.group(1))
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            ApiError(
                error="not_found",
                message=f"No route matches GET {path}.",
            ),
        )

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/oauth/token":
            self._handle_token()
            return

        if path == "/oauth/revoke":
            self._handle_revoke()
            return

        items_match = CATALOG_ITEMS_PATH.fullmatch(path)
        if items_match:
            self._handle_catalog_item_create(items_match.group(1))
            return

        refresh_match = CACHE_REFRESH_PATH.fullmatch(path)
        if refresh_match:
            self._handle_cache_refresh(refresh_match.group(1))
            return

        members_match = MEMBERS_PATH.fullmatch(path)
        if members_match:
            self._handle_member_create(members_match.group(1))
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            ApiError(
                error="not_found",
                message=f"No route matches POST {path}.",
            ),
        )

    def do_PATCH(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        member_match = MEMBER_PATH.fullmatch(path)
        if member_match:
            self._handle_member_update(
                member_match.group(1),
                int(member_match.group(2)),
            )
            return

        item_match = CATALOG_ITEM_PATH.fullmatch(path)
        if item_match:
            self._handle_catalog_item_update(
                item_match.group(1),
                int(item_match.group(2)),
            )
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            ApiError(
                error="not_found",
                message=f"No route matches PATCH {path}.",
            ),
        )

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        member_match = MEMBER_PATH.fullmatch(path)
        if member_match:
            self._handle_member_delete(
                member_match.group(1),
                int(member_match.group(2)),
            )
            return

        item_match = CATALOG_ITEM_PATH.fullmatch(path)
        if item_match:
            self._handle_catalog_item_delete(
                item_match.group(1),
                int(item_match.group(2)),
            )
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            ApiError(
                error="not_found",
                message=f"No route matches DELETE {path}.",
            ),
        )

    def _handle_readiness(self) -> None:
        checks: dict[str, HealthCheck] = {}

        for name, check in (
            ("postgres", _postgres_check),
            ("redis", _redis_check),
        ):
            try:
                checks[name] = HealthCheck.model_validate(check())
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Readiness check failed for %s: %s", name, exc)
                checks[name] = HealthCheck(
                    status="error",
                    error=type(exc).__name__,
                )

        ready = all(check.status == "ok" for check in checks.values())
        status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
        self._send_json(
            status,
            ReadinessResponse(
                status="ready" if ready else "degraded",
                checks=checks,
            ),
        )

    def _handle_catalog(self, slug: str) -> None:
        try:
            status, payload, headers = _catalog_with_cache(slug)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Catalog query failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(
                    error="database_unavailable",
                    message=type(exc).__name__,
                ),
            )
            return

        self._send_json(status, payload, headers=headers)

    def _handle_cache_refresh(self, slug: str) -> None:
        """Queue an asynchronous cache refresh and answer with the job id."""

        user = self._authorize_catalog_write(slug)
        if user is None:
            return

        payload = self._read_json_payload()
        if payload is None:
            return

        client_id = self.headers.get("X-QA-Client-Id") or self.client_address[0]
        budget = _consume_write_budget(
            client_id,
            int(user["id"]),
        )
        # Every response on a budgeted endpoint echoes the budget, not just the
        # 201 and the 429: a client should be able to pace itself from any reply.
        budget_headers = _rate_limit_headers(budget)
        if budget.limited:
            self._send_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                ApiError(
                    error="rate_limited",
                    message=f"Too many catalog writes for this {budget.scope}.",
                ),
                headers=budget_headers,
            )
            return

        try:
            request = validate_contract(CacheRefreshRequest, payload)
        except ContractValidationError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                _validation_error_payload(exc),
                headers=budget_headers,
            )
            return

        try:
            record = _enqueue_job(
                job_type="catalog.cache_refresh",
                workspace_slug=slug,
                payload={"ttl_seconds": request.ttl_seconds},
                delay_seconds=request.delay_seconds,
            )
        except redis.RedisError as exc:
            LOGGER.warning("Queueing the cache refresh failed: %s", exc)
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="queue_unavailable", message=type(exc).__name__),
                headers=budget_headers,
            )
            return

        job_id = str(record["job_id"])
        self._send_json(
            HTTPStatus.ACCEPTED,
            JobAcceptedResponse(
                job_id=job_id,
                type=str(record["type"]),
                workspace_slug=slug,
                status="queued",
                queued_at=str(record["queued_at"]),
            ),
            headers={
                "Location": f"/api/v1/jobs/{job_id}",
                **budget_headers,
            },
        )

    def _handle_job_queue_stats(self) -> None:
        user = self._authenticated_user()
        if user is None:
            return
        try:
            stats = _job_queue_stats()
        except redis.RedisError as exc:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="queue_unavailable", message=type(exc).__name__),
            )
            return
        self._send_json(HTTPStatus.OK, stats)

    def _handle_job(self, job_id: str) -> None:
        """Return one job, but only to the workspace that queued it."""

        user = self._authenticated_user()
        if user is None:
            return

        try:
            record = _load_job(job_id)
        except redis.RedisError as exc:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="queue_unavailable", message=type(exc).__name__),
            )
            return
        if record is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="job_not_found",
                    message=f"Job '{job_id}' was not found.",
                ),
            )
            return

        try:
            workspace = _workspace_by_slug(str(record["workspace_slug"]))
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Job workspace lookup failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="database_unavailable", message=type(exc).__name__),
            )
            return
        if workspace is None or workspace["id"] != user["workspace_id"]:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                ApiError(
                    error="permission_denied",
                    message="The authenticated user cannot read this job.",
                ),
            )
            return
        self._send_json(HTTPStatus.OK, _job_response(record))

    def _handle_events(self, slug: str) -> None:
        """Upgrade to WebSocket and stream this workspace's events."""

        user = self._authenticated_user()
        if user is None:
            return

        if self.headers.get("Upgrade", "").strip().lower() != "websocket":
            self._send_json(
                HTTPStatus.UPGRADE_REQUIRED,
                ApiError(
                    error="websocket_upgrade_required",
                    message="This endpoint only answers a WebSocket upgrade.",
                ),
            )
            return

        key = self.headers.get("Sec-WebSocket-Key", "")
        version = self.headers.get("Sec-WebSocket-Version", "")
        if not key or version != "13":
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                ApiError(
                    error="invalid_websocket_handshake",
                    message="Sec-WebSocket-Key and Sec-WebSocket-Version: 13 are required.",
                ),
            )
            return

        try:
            workspace = _workspace_by_slug(slug)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Event stream workspace lookup failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="database_unavailable", message=type(exc).__name__),
            )
            return
        if workspace is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="workspace_not_found",
                    message=f"Workspace '{slug}' was not found.",
                ),
            )
            return
        if workspace["id"] != user["workspace_id"]:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                ApiError(
                    error="permission_denied",
                    message="The authenticated user cannot read another workspace's events.",
                ),
            )
            return

        self._send_switching_protocols(key)
        self._stream_events(slug)

    def _send_switching_protocols(self, key: str) -> None:
        """Answer the WebSocket handshake with 101 and stop using HTTP framing."""

        self.send_response(HTTPStatus.SWITCHING_PROTOCOLS.value)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", websocket_accept(key))
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True

    def _stream_events(self, slug: str) -> None:
        """Push queued events until the client closes the stream."""

        channel = EVENT_BROKER.subscribe(slug)
        stop = threading.Event()
        write_lock = threading.Lock()

        def read_until_closed() -> None:
            try:
                while not stop.is_set():
                    frame = read_ws_frame(self.rfile)
                    if frame is None:
                        break
                    opcode, payload = frame
                    if opcode == WS_OPCODE_CLOSE:
                        break
                    if opcode == WS_OPCODE_PING:
                        with write_lock:
                            self.wfile.write(encode_ws_frame(payload, opcode=WS_OPCODE_PONG))
                            self.wfile.flush()
            except (OSError, ValueError):
                pass
            finally:
                stop.set()

        reader = threading.Thread(
            target=read_until_closed,
            name=f"ws-reader-{slug}",
            daemon=True,
        )
        reader.start()
        LOGGER.info("Event subscriber attached to %s", slug)

        delivered = 0
        try:
            while not stop.is_set():
                try:
                    event = channel.get(timeout=WS_POLL_SECONDS)
                except queue.Empty:
                    continue
                with write_lock:
                    self.wfile.write(encode_ws_text(json.dumps(event, sort_keys=True)))
                    self.wfile.flush()
                delivered += 1
        except OSError:
            pass
        finally:
            stop.set()
            EVENT_BROKER.unsubscribe(slug, channel)
            LOGGER.info(
                "Event subscriber detached from %s after %s events",
                slug,
                delivered,
            )

    def _workspace_scope(
        self,
        slug: str,
        capability: str,
        *,
        denied_message: str,
        cross_tenant_message: str,
    ) -> dict[str, Any] | None:
        """Authenticate, authorize, and tenant-check one workspace request.

        The order matters and is part of the contract: an unknown but
        syntactically valid object is 404, a role that lacks the capability is
        403, and an object that belongs to another tenant is also 403 because
        workspace slugs are already public through the read catalog endpoint.
        """

        if not WORKSPACE_SLUG_PATTERN.match(slug):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                ApiError(
                    error="invalid_workspace_slug",
                    message=(
                        "A workspace slug must be 1-60 lowercase letters, "
                        "digits, or hyphens, and may not start or end with a "
                        "hyphen."
                    ),
                ),
            )
            return None
        user = self._authenticated_user()
        if user is None:
            return None
        if not has_capability(str(user["role"]), capability):
            self._send_json(
                HTTPStatus.FORBIDDEN,
                ApiError(
                    error="permission_denied",
                    message=denied_message,
                ),
            )
            return None
        try:
            workspace = _workspace_by_slug(slug)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Workspace lookup failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(
                    error="database_unavailable",
                    message=type(exc).__name__,
                ),
            )
            return None
        if workspace is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="workspace_not_found",
                    message=f"Workspace '{slug}' was not found.",
                ),
            )
            return None
        if workspace["id"] != user["workspace_id"]:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                ApiError(
                    error="permission_denied",
                    message=cross_tenant_message,
                ),
            )
            return None
        return {"user": user, "workspace": workspace}

    def _authorize_catalog_write(self, slug: str) -> dict[str, Any] | None:
        scope = self._workspace_scope(
            slug,
            "catalog:write",
            denied_message="The authenticated role cannot modify the catalog.",
            cross_tenant_message=(
                "The authenticated user cannot modify another workspace."
            ),
        )
        return None if scope is None else scope["user"]

    def _handle_permissions(self) -> None:
        """Describe the caller's role as capabilities instead of a role name."""

        user = self._authenticated_user()
        if user is None:
            return
        self._send_json(
            HTTPStatus.OK,
            PermissionsResponse(
                user_id=int(user["id"]),
                workspace_slug=str(user["workspace_slug"]),
                role=str(user["role"]),
                capabilities=capabilities_for(str(user["role"])),
            ),
        )

    def _handle_members_list(self, slug: str) -> None:
        scope = self._workspace_scope(
            slug,
            "members:read",
            denied_message="The authenticated role cannot read workspace members.",
            cross_tenant_message=(
                "The authenticated user cannot read another workspace's members."
            ),
        )
        if scope is None:
            return

        try:
            rows = _workspace_members(int(scope["workspace"]["id"]))
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Member list failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="database_unavailable", message=type(exc).__name__),
            )
            return

        members = [_member_payload(row) for row in rows]
        self._send_json(
            HTTPStatus.OK,
            MembersResponse(
                workspace_slug=str(scope["workspace"]["slug"]),
                count=len(members),
                members=members,
            ),
        )

    def _handle_member_create(self, slug: str) -> None:
        scope = self._workspace_scope(
            slug,
            "members:write",
            denied_message="The authenticated role cannot add workspace members.",
            cross_tenant_message=(
                "The authenticated user cannot add members to another workspace."
            ),
        )
        if scope is None:
            return

        payload = self._read_json_payload()
        if payload is None:
            return

        try:
            request = validate_contract(MemberCreate, payload)
        except ContractValidationError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                _validation_error_payload(exc),
            )
            return

        user = scope["user"]
        if request.role == "admin" and user["role"] != "owner":
            self._send_json(
                HTTPStatus.FORBIDDEN,
                ApiError(
                    error="role_escalation_forbidden",
                    message="Only an owner can grant the admin role.",
                ),
            )
            return

        try:
            member = _insert_workspace_member(
                int(scope["workspace"]["id"]),
                request,
            )
        except psycopg.errors.UniqueViolation:
            self._send_json(
                HTTPStatus.CONFLICT,
                ApiError(
                    error="member_conflict",
                    message=(
                        f"'{request.email}' already belongs to this workspace."
                    ),
                ),
            )
            return
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Member invite failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="database_unavailable", message=type(exc).__name__),
            )
            return

        self._send_json(
            HTTPStatus.CREATED,
            member,
            headers={
                "Location": (
                    f"/api/v1/workspaces/{scope['workspace']['slug']}"
                    f"/members/{member.id}"
                )
            },
        )

    def _handle_member_update(self, slug: str, user_id: int) -> None:
        scope = self._workspace_scope(
            slug,
            "members:write",
            denied_message="The authenticated role cannot change member roles.",
            cross_tenant_message=(
                "The authenticated user cannot change another workspace's members."
            ),
        )
        if scope is None:
            return

        payload = self._read_json_payload()
        if payload is None:
            return

        try:
            request = validate_contract(MemberRoleUpdate, payload)
        except ContractValidationError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                _validation_error_payload(exc),
            )
            return

        guard = self._guard_member_mutation(scope, user_id, request.role)
        if guard is None:
            return

        try:
            member = _update_member_role(
                int(scope["workspace"]["id"]),
                user_id,
                request.role,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Member role update failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="database_unavailable", message=type(exc).__name__),
            )
            return

        if member is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="member_not_found",
                    message=f"Member {user_id} was not found in '{slug}'.",
                ),
            )
            return

        self._send_json(HTTPStatus.OK, member)

    def _handle_member_delete(self, slug: str, user_id: int) -> None:
        scope = self._workspace_scope(
            slug,
            "members:write",
            denied_message="The authenticated role cannot remove workspace members.",
            cross_tenant_message=(
                "The authenticated user cannot remove another workspace's members."
            ),
        )
        if scope is None:
            return

        guard = self._guard_member_mutation(scope, user_id, target_role=None)
        if guard is None:
            return

        try:
            deleted = _delete_workspace_member(
                int(scope["workspace"]["id"]),
                user_id,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Member removal failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="database_unavailable", message=type(exc).__name__),
            )
            return

        if not deleted:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="member_not_found",
                    message=f"Member {user_id} was not found in '{slug}'.",
                ),
            )
            return
        self._send_empty(HTTPStatus.NO_CONTENT)

    def _guard_member_mutation(
        self,
        scope: dict[str, Any],
        user_id: int,
        target_role: str | None,
    ) -> dict[str, Any] | None:
        """Apply the owner-protection rules shared by PATCH and DELETE.

        Returns the targeted member row when the mutation may proceed, and
        answers with the documented 403/404 when it may not.
        """

        try:
            member = _workspace_member(
                int(scope["workspace"]["id"]),
                user_id,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Member lookup failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="database_unavailable", message=type(exc).__name__),
            )
            return None

        if member is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="member_not_found",
                    message=(
                        f"Member {user_id} was not found in "
                        f"'{scope['workspace']['slug']}'."
                    ),
                ),
            )
            return None
        if str(member["role"]) == "owner":
            self._send_json(
                HTTPStatus.FORBIDDEN,
                ApiError(
                    error="owner_protected",
                    message=(
                        "An owner membership cannot be changed or removed "
                        "through the members API."
                    ),
                ),
            )
            return None
        if int(member["id"]) == int(scope["user"]["id"]):
            self._send_json(
                HTTPStatus.FORBIDDEN,
                ApiError(
                    error="self_modification_forbidden",
                    message="A member cannot change or remove its own membership.",
                ),
            )
            return None
        if (
            target_role == "admin"
            and scope["user"]["role"] != "owner"
        ):
            self._send_json(
                HTTPStatus.FORBIDDEN,
                ApiError(
                    error="role_escalation_forbidden",
                    message="Only an owner can grant the admin role.",
                ),
            )
            return None
        return member

    def _handle_catalog_item_read(self, slug: str, item_id: int) -> None:
        """Read one catalog item inside the caller's own workspace.

        Item ids are sequential across tenants, so a foreign id must be
        indistinguishable from an unknown one: both answer 404.
        """

        scope = self._workspace_scope(
            slug,
            "catalog:read",
            denied_message="The authenticated role cannot read the catalog.",
            cross_tenant_message=(
                "The authenticated user cannot read another workspace's catalog."
            ),
        )
        if scope is None:
            return

        try:
            item = _catalog_item_by_id(int(scope["workspace"]["id"]), item_id)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Catalog item read failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(error="database_unavailable", message=type(exc).__name__),
            )
            return

        if item is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="item_not_found",
                    message=(
                        f"Catalog item {item_id} was not found in "
                        f"'{scope['workspace']['slug']}'."
                    ),
                ),
            )
            return
        self._send_json(
            HTTPStatus.OK,
            CatalogItem(
                id=int(item["id"]),
                sku=str(item["sku"]),
                name=str(item["name"]),
                price_cents=int(item["price_cents"]),
                status=str(item["status"]),
            ),
        )

    def _handle_catalog_item_create(self, slug: str) -> None:
        user = self._authorize_catalog_write(slug)
        if user is None:
            return

        payload = self._read_json_payload()
        if payload is None:
            return

        client_id = self.headers.get("X-QA-Client-Id") or self.client_address[0]
        budget = _consume_write_budget(
            client_id,
            int(user["id"]),
        )
        budget_headers = _rate_limit_headers(budget)
        if budget.limited:
            self._send_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                ApiError(
                    error="rate_limited",
                    message=(
                        "Too many catalog writes for this "
                        f"{budget.scope}."
                    ),
                ),
                headers=budget_headers,
            )
            return

        try:
            request = validate_contract(CatalogItemCreate, payload)
        except ContractValidationError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                _validation_error_payload(exc),
                headers=budget_headers,
            )
            return

        idempotency_key = self.headers.get("Idempotency-Key")
        store_key = (
            _idempotency_store_key(user["workspace_id"], idempotency_key)
            if idempotency_key
            else None
        )
        fingerprint = _body_fingerprint(request.model_dump(mode="json"))
        if store_key is not None:
            cached = _read_idempotent_response(store_key)
            if cached is not None:
                if cached.get("fingerprint") != fingerprint:
                    self._send_json(
                        HTTPStatus.CONFLICT,
                        ApiError(
                            error="idempotency_conflict",
                            message=(
                                "The Idempotency-Key was already used with a "
                                "different request body."
                            ),
                        ),
                        headers=budget_headers,
                    )
                    return
                raw_status = cached.get("status_code", HTTPStatus.OK.value)
                cached_payload = cached.get("payload")
                self._send_json(
                    HTTPStatus(int(raw_status)),
                    cached_payload if isinstance(cached_payload, dict) else {},
                    headers={"Idempotent-Replay": "true", **budget_headers},
                )
                return

        try:
            item = _create_catalog_item(user["workspace_id"], request)
        except psycopg.errors.UniqueViolation:
            self._send_json(
                HTTPStatus.CONFLICT,
                ApiError(
                    error="sku_conflict",
                    message=(
                        f"SKU '{request.sku}' already exists in this workspace."
                    ),
                ),
                headers=budget_headers,
            )
            return
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Catalog item create failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(
                    error="database_unavailable",
                    message=type(exc).__name__,
                ),
                headers=budget_headers,
            )
            return

        if store_key is not None:
            _store_idempotent_response(
                store_key,
                fingerprint=fingerprint,
                status_code=HTTPStatus.CREATED.value,
                payload=item.model_dump(mode="json"),
            )
        _invalidate_catalog_cache(slug)
        EVENT_BROKER.publish(
            slug,
            "catalog.item.created",
            {"item": item.model_dump(mode="json"), "cache_invalidated": True},
        )
        self._send_json(
            HTTPStatus.CREATED,
            item,
            headers={
                "Location": f"/api/v1/workspaces/{slug}/catalog/items/{item.id}",
                **budget_headers,
            },
        )

    def _handle_catalog_item_update(self, slug: str, item_id: int) -> None:
        user = self._authorize_catalog_write(slug)
        if user is None:
            return

        payload = self._read_json_payload()
        if payload is None:
            return

        try:
            request = validate_contract(CatalogItemStatusUpdate, payload)
        except ContractValidationError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                _validation_error_payload(exc),
            )
            return

        try:
            current = _catalog_item_by_id(user["workspace_id"], item_id)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Catalog item lookup failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(
                    error="database_unavailable",
                    message=type(exc).__name__,
                ),
            )
            return

        if current is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="item_not_found",
                    message=f"Catalog item {item_id} was not found in '{slug}'.",
                ),
            )
            return

        current_status = current["status"]
        target_status = request.status
        if (current_status, target_status) not in ALLOWED_STATUS_TRANSITIONS:
            self._send_json(
                HTTPStatus.CONFLICT,
                ApiError(
                    error="invalid_state_transition",
                    message=(
                        f"Cannot move catalog item {item_id} from "
                        f"'{current_status}' to '{target_status}'."
                    ),
                ),
            )
            return

        try:
            updated = _update_catalog_item_status(
                user["workspace_id"],
                item_id,
                target_status,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Catalog item update failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(
                    error="database_unavailable",
                    message=type(exc).__name__,
                ),
            )
            return

        if updated is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="item_not_found",
                    message=f"Catalog item {item_id} was not found in '{slug}'.",
                ),
            )
            return
        _invalidate_catalog_cache(slug)
        EVENT_BROKER.publish(
            slug,
            "catalog.item.updated",
            {"item": updated.model_dump(mode="json"), "cache_invalidated": True},
        )
        self._send_json(HTTPStatus.OK, updated)

    def _handle_catalog_item_delete(self, slug: str, item_id: int) -> None:
        user = self._authorize_catalog_write(slug)
        if user is None:
            return

        try:
            deleted = _delete_catalog_item(user["workspace_id"], item_id)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Catalog item delete failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ApiError(
                    error="database_unavailable",
                    message=type(exc).__name__,
                ),
            )
            return

        if not deleted:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                ApiError(
                    error="item_not_found",
                    message=f"Catalog item {item_id} was not found in '{slug}'.",
                ),
            )
            return
        _invalidate_catalog_cache(slug)
        EVENT_BROKER.publish(
            slug,
            "catalog.item.deleted",
            {"item_id": item_id, "cache_invalidated": True},
        )
        self._send_empty(HTTPStatus.NO_CONTENT)

    def _handle_token(self) -> None:
        try:
            payload = self._read_request_payload(strict_media_type=False)
        except RequestBodyError as exc:
            self._send_oauth_error(exc.status, "invalid_request", exc.message)
            return
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
            client_id = self.headers.get("X-QA-Client-Id") or self.client_address[0]
            failure_key = _signin_failure_key(client_id, username)
            retry_after = _signin_retry_after(failure_key)
            if retry_after is not None:
                self._send_json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    OAuthErrorResponse(
                        error="rate_limited",
                        error_description=(
                            "Too many failed sign-in attempts for this "
                            "account; retry after the window expires."
                        ),
                    ),
                    headers={
                        "Retry-After": str(max(1, math.ceil(retry_after))),
                    },
                )
                return
            user = _authenticate_password(username, password)
            if user is None:
                _record_signin_failure(failure_key)
                self._send_oauth_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_grant",
                    "username or password is invalid",
                )
                return
            _clear_signin_failures(failure_key)
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
        access_token = token_payload.access_token
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
            payload = self._read_request_payload(strict_media_type=False)
        except RequestBodyError as exc:
            self._send_oauth_error(exc.status, "invalid_request", exc.message)
            return
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
            RevokeResponse(revoked=True),
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
                ApiError(
                    error="permission_denied",
                    message="The authenticated role cannot read the audit view.",
                ),
            )
            return
        self._send_json(
            HTTPStatus.OK,
            AdminAuditResponse(
                workspace_slug=user["workspace_slug"],
                role=user["role"],
                events=["workspace.created", "user.invited"],
            ),
        )

    def _authenticated_user(self) -> dict[str, Any] | None:
        token = self._access_token()
        if token is None:
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                ApiError(
                    error="authentication_required",
                    message="Provide a Bearer token or access cookie.",
                ),
            )
            return None

        try:
            claims = _decode_access_token(token, now=int(time.time()))
            user_id = int(claims["sub"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                ApiError(
                    error="invalid_token",
                    message="The access token is invalid or expired.",
                ),
            )
            return None

        user = _find_user_by_id(user_id)
        if user is None or user["status"] != "active":
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                ApiError(
                    error="invalid_token",
                    message="The token user is missing or disabled.",
                ),
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

    def _read_request_payload(
        self,
        *,
        strict_media_type: bool = True,
    ) -> dict[str, Any]:
        """Read a small JSON or form body, refusing hostile shapes early.

        ``strict_media_type`` controls how an unreadable ``Content-Type`` is
        reported: the JSON API answers 415, while the OAuth2 endpoints keep the
        RFC 6749 habit of a 400 ``invalid_request``.
        """

        raw_length = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Content-Length must be an integer") from exc
        if content_length < 0:
            raise ValueError("Content-Length cannot be negative")
        if content_length > MAX_REQUEST_BYTES:
            # Drain a bounded amount so the client is not left mid-request, then
            # close the connection: the rest of the body is never read.
            self._drain_request_body(min(content_length, MAX_REQUEST_BYTES + 8192))
            self.close_connection = True
            raise RequestBodyError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "payload_too_large",
                (
                    f"Request body must not exceed {MAX_REQUEST_BYTES} bytes; "
                    f"received {content_length}."
                ),
            )

        raw_body = self.rfile.read(content_length) if content_length else b""
        if not raw_body:
            return {}

        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type == "application/x-www-form-urlencoded":
            fields = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
            return {name: values[-1] for name, values in fields.items()}
        if media_type == "application/json":
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except RecursionError as exc:
                # Deeply nested JSON is a body problem, not a server crash.
                raise ValueError("JSON request body is nested too deeply") from exc
            if not isinstance(payload, dict):
                raise ValueError("JSON request body must be an object")
            return payload
        if strict_media_type:
            raise RequestBodyError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "unsupported_media_type",
                (
                    "This endpoint reads application/json; received "
                    f"{media_type or '<missing>'}."
                ),
            )
        raise ValueError(f"unsupported Content-Type: {media_type or '<missing>'}")

    def _drain_request_body(self, limit: int) -> None:
        """Discard up to ``limit`` bytes of an oversized request body."""

        remaining = limit
        while remaining > 0:
            chunk = self.rfile.read(min(8192, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def _read_json_payload(self) -> dict[str, Any] | None:
        """Read a JSON API body, answering 400/413/415 on the way out."""

        try:
            return self._read_request_payload()
        except RequestBodyError as exc:
            self._send_json(
                exc.status,
                ApiError(error=exc.error, message=exc.message),
                # An oversized body is not drained in full, so the connection
                # cannot be reused for a second request.
                headers=(
                    {"Connection": "close"}
                    if exc.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
                    else None
                ),
            )
            return None
        except (UnicodeDecodeError, ValueError) as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                ApiError(error="invalid_request", message=str(exc)),
            )
            return None

    def _send_oauth_error(
        self,
        status: HTTPStatus,
        error: str,
        description: str,
    ) -> None:
        self._send_json(
            status,
            OAuthErrorResponse(
                error=error,
                error_description=description,
            ),
        )

    def _send_empty(self, status: HTTPStatus) -> None:
        self.send_response(status.value)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _send_json(
        self,
        status: HTTPStatus,
        payload: ResponsePayload,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        payload_dict = (
            payload.model_dump(mode="json")
            if isinstance(payload, BaseModel)
            else payload
        )
        body = json.dumps(
            payload_dict,
            ensure_ascii=True,
            sort_keys=True,
        ).encode("utf-8")
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
    worker: JobWorker | None = None
    if JOB_WORKER_ENABLED:
        worker = JobWorker(EVENT_BROKER)
        worker.start()
    else:
        LOGGER.warning("Job worker is disabled; queued jobs stay queued")

    server = ThreadingHTTPServer(("0.0.0.0", port), SutRequestHandler)
    LOGGER.info("SUT API listening on port %s", port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("SUT API interrupted")
    finally:
        if worker is not None:
            worker.stop()
        server.server_close()


if __name__ == "__main__":
    main()
