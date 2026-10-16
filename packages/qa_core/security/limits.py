"""Read rate-limit budgets and the sign-in throttle from the test side."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import httpx
import redis

SIGNIN_FAILURE_PREFIX = "auth:signin-failures:"
WRITE_BUDGET_PRINCIPAL_PREFIX = "ratelimit:write:principal:"
WRITE_BUDGET_CLIENT_PREFIX = "ratelimit:write:client:"
RATE_LIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
RATE_LIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
RATE_LIMIT_RESET_HEADER = "X-RateLimit-Reset"
RATE_LIMIT_SCOPE_HEADER = "X-RateLimit-Scope"


@dataclass(frozen=True)
class RateLimitBudget:
    """The budget numbers one response advertised."""

    limit: int
    remaining: int
    reset_after: int
    scope: str

    @property
    def exhausted(self) -> bool:
        """Return whether the advertised bucket has no room left."""

        return self.remaining <= 0


def parse_rate_limit_headers(response: httpx.Response) -> RateLimitBudget | None:
    """Parse the budget headers, returning ``None`` when they are absent."""

    limit = response.headers.get(RATE_LIMIT_LIMIT_HEADER)
    remaining = response.headers.get(RATE_LIMIT_REMAINING_HEADER)
    reset_after = response.headers.get(RATE_LIMIT_RESET_HEADER)
    scope = response.headers.get(RATE_LIMIT_SCOPE_HEADER)
    if limit is None or remaining is None or reset_after is None or scope is None:
        return None
    return RateLimitBudget(
        limit=int(limit),
        remaining=int(remaining),
        reset_after=int(reset_after),
        scope=scope,
    )


def retry_after_seconds(response: httpx.Response) -> int | None:
    """Return the ``Retry-After`` header in whole seconds when it is present."""

    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return math.ceil(float(raw))
    except ValueError:
        return None


def signin_failure_key(client_id: str, email: str) -> str:
    """Return the Redis key the SUT uses for one (client, account) pair."""

    digest = hashlib.sha256(f"{client_id}|{email.lower()}".encode()).hexdigest()
    return f"{SIGNIN_FAILURE_PREFIX}{digest[:32]}"


def client_budget_key(client_id: str) -> str:
    """Return the Redis key the SUT uses for one client id's write budget."""

    return f"{WRITE_BUDGET_CLIENT_PREFIX}{hashlib.sha256(client_id.encode()).hexdigest()[:32]}"


def principal_budget_key(user_id: int) -> str:
    """Return the Redis key the SUT uses for one principal's write budget."""

    return f"{WRITE_BUDGET_PRINCIPAL_PREFIX}user:{user_id}"


def purge_write_budget(redis_url: str, user_ids: list[int]) -> int:
    """Delete the write budgets of the given principals.

    A leased namespace hands the same owner user back to the next test, so the
    pooled budget would otherwise leak between tests. The counter is
    infrastructure state, not test data, so it is cleared on release just like
    the Week 10 catalog cache keys.
    """

    if not user_ids:
        return 0
    client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        return int(
            client.delete(*[principal_budget_key(user_id) for user_id in user_ids])
        )
    except redis.RedisError:
        return 0
    finally:
        client.close()


class SignInThrottleProbe:
    """Inspect the failed sign-in counter that backs the token-endpoint 429."""

    def __init__(self, redis_url: str) -> None:
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    def close(self) -> None:
        """Close the probe's Redis connection."""

        self._client.close()

    def failures(self, *, client_id: str, email: str) -> int:
        """Return how many failures are currently counted, 0 when absent."""

        raw = self._client.get(signin_failure_key(client_id, email))
        return int(raw) if raw is not None else 0

    def ttl_seconds(self, *, client_id: str, email: str) -> int:
        """Return the remaining window in seconds, -2 when the key is gone."""

        return int(self._client.ttl(signin_failure_key(client_id, email)))

    def clear(self, *, client_id: str, email: str) -> None:
        """Delete the counter so a test cannot leak state into the next one."""

        self._client.delete(signin_failure_key(client_id, email))
