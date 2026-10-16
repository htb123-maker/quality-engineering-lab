"""Inspect the Week 10 catalog cache without going through the API.

The SUT writes its cache entries and counters with fixed key names, so a test
can assert on the real Redis state instead of trusting an HTTP header: an entry
with a TTL, a negative entry for a missing workspace, and counters that prove
how many reads actually reached PostgreSQL.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import redis

CATALOG_CACHE_PREFIX = "cache:catalog"
CACHE_STATS_PREFIX = "cache:stats"
DEFAULT_TTL_SECONDS = 60
DEFAULT_NEGATIVE_TTL_SECONDS = 10
STAT_NAMES = ("hit", "hit_negative", "miss", "db_reads", "invalidations")


def catalog_cache_key(workspace_slug: str) -> str:
    """Return the Redis key that caches one workspace catalog."""

    return f"{CATALOG_CACHE_PREFIX}:{workspace_slug}"


def catalog_absent_cache_key(workspace_slug: str) -> str:
    """Return the Redis key that caches a "workspace not found" answer."""

    return f"{CATALOG_CACHE_PREFIX}:{workspace_slug}:absent"


def catalog_cache_pattern(workspace_slug: str) -> str:
    """Return the Redis match pattern for every key of one workspace."""

    return f"{CATALOG_CACHE_PREFIX}:{workspace_slug}*"


def cache_stats_key(workspace_slug: str, name: str) -> str:
    """Return the Redis key that counts one cache outcome."""

    return f"{CACHE_STATS_PREFIX}:{workspace_slug}:{name}"


def open_redis(redis_url: str) -> redis.Redis:
    """Open a short-lived Redis client with the project's local timeouts."""

    return redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


@dataclass(frozen=True)
class CacheEntry:
    """One cached value with the TTL that Redis reports for it."""

    key: str
    payload: dict[str, Any]
    ttl_seconds: int

    @property
    def expires(self) -> bool:
        """Return whether the entry carries a real expiry."""

        return self.ttl_seconds > 0


def read_cache_entry(redis_url: str, key: str) -> CacheEntry | None:
    """Return one cached entry, or ``None`` when the key is absent."""

    client = open_redis(redis_url)
    try:
        raw = client.get(key)
        ttl = int(client.ttl(key))
    finally:
        client.close()
    if raw is None:
        return None
    payload: Any = _loads(raw)
    if not isinstance(payload, dict):
        return None
    return CacheEntry(key=key, payload=payload, ttl_seconds=ttl)


def read_catalog_cache(redis_url: str, workspace_slug: str) -> CacheEntry | None:
    """Return the cached catalog of one workspace."""

    return read_cache_entry(redis_url, catalog_cache_key(workspace_slug))


def read_absent_cache(redis_url: str, workspace_slug: str) -> CacheEntry | None:
    """Return the cached "workspace not found" answer, when it exists."""

    return read_cache_entry(redis_url, catalog_absent_cache_key(workspace_slug))


def cache_keys(redis_url: str, workspace_slug: str) -> list[str]:
    """Return every cache key that belongs to one workspace."""

    client = open_redis(redis_url)
    try:
        return sorted(
            str(key)
            for key in client.scan_iter(match=catalog_cache_pattern(workspace_slug))
        )
    finally:
        client.close()


def read_cache_stats(redis_url: str, workspace_slug: str) -> dict[str, int]:
    """Return the cache counters of one workspace, defaulting missing ones to 0."""

    client = open_redis(redis_url)
    try:
        with client.pipeline() as pipe:
            for name in STAT_NAMES:
                pipe.get(cache_stats_key(workspace_slug, name))
            values = pipe.execute()
    finally:
        client.close()
    return {
        name: int(value or 0)
        for name, value in zip(STAT_NAMES, values, strict=True)
    }


def purge_catalog_cache(redis_url: str, workspace_slug: str) -> int:
    """Delete every cache key and counter of one workspace.

    Namespaces are purged at teardown, but a cache entry lives under a different
    key space, so the same cleanup rule has to be applied here as well.
    """

    deleted = 0
    client = open_redis(redis_url)
    try:
        batch: list[str] = []
        for key in client.scan_iter(match=catalog_cache_pattern(workspace_slug)):
            batch.append(str(key))
            if len(batch) >= 100:
                deleted += int(client.delete(*batch))
                batch.clear()
        if batch:
            deleted += int(client.delete(*batch))
        with client.pipeline() as pipe:
            for name in STAT_NAMES:
                pipe.delete(cache_stats_key(workspace_slug, name))
            pipe.execute()
    finally:
        client.close()
    return deleted


def ttl_seconds_remaining(redis_url: str, key: str) -> int:
    """Return the remaining TTL of one key, or -2 when the key does not exist."""

    client = open_redis(redis_url)
    try:
        return int(client.ttl(key))
    finally:
        client.close()


@dataclass(frozen=True)
class CatalogCacheProbe:
    """Read, shorten, and clean the cache entries of one workspace."""

    redis_url: str
    workspace_slug: str

    def entry(self) -> CacheEntry | None:
        """Return the cached catalog, when it exists."""

        return read_catalog_cache(self.redis_url, self.workspace_slug)

    def absent_entry(self) -> CacheEntry | None:
        """Return the cached "workspace not found" answer, when it exists."""

        return read_absent_cache(self.redis_url, self.workspace_slug)

    def stats(self) -> dict[str, int]:
        """Return the hit, miss, and invalidations counters."""

        return read_cache_stats(self.redis_url, self.workspace_slug)

    def keys(self) -> list[str]:
        """Return every cache key of this workspace."""

        return cache_keys(self.redis_url, self.workspace_slug)

    def purge(self) -> int:
        """Delete every cache key and counter of this workspace."""

        return purge_catalog_cache(self.redis_url, self.workspace_slug)

    def expire_soon(self, key: str, *, seconds: int = 1) -> bool:
        """Overwrite one key's TTL so an expiry test does not wait a minute."""

        client = open_redis(self.redis_url)
        try:
            return bool(client.expire(key, seconds))
        finally:
            client.close()

    def wait_until_expired(
        self,
        key: str,
        *,
        timeout: float = 5.0,
        interval: float = 0.05,
    ) -> bool:
        """Poll until Redis reports the key as missing, or the deadline passes."""

        deadline = time.monotonic() + timeout
        while True:
            if ttl_seconds_remaining(self.redis_url, key) == -2:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)


def _loads(raw: bytes | str) -> Any:
    """Parse a cached JSON document, returning ``None`` when it is unusable."""

    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
