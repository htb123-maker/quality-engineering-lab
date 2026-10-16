"""Remove the Redis keys that Week 7 idempotency tests leave behind."""

from __future__ import annotations

import redis

IDEMPOTENCY_KEY_PREFIX = "idem:"


def idempotency_key_pattern(workspace_id: int) -> str:
    """Return the Redis match pattern for one workspace's idempotency keys."""

    return f"{IDEMPOTENCY_KEY_PREFIX}{workspace_id}:*"


def purge_idempotency_keys(
    redis_url: str,
    workspace_id: int,
    *,
    batch_size: int = 100,
) -> int:
    """Delete one workspace's idempotency keys and return the deleted count.

    Idempotency records expire on their own, but a repeated test run should not
    depend on the TTL. Keys are scanned in batches so the cleanup stays cheap
    when other workspaces hold unrelated keys.
    """

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    deleted = 0
    batch: list[str] = []
    try:
        for key in client.scan_iter(
            match=idempotency_key_pattern(workspace_id),
            count=batch_size,
        ):
            batch.append(str(key))
            if len(batch) >= batch_size:
                deleted += int(client.delete(*batch))
                batch.clear()
        if batch:
            deleted += int(client.delete(*batch))
    finally:
        client.close()
    return deleted
