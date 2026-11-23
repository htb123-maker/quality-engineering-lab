"""Redis read-model and idempotency helpers for commerce tests."""

from __future__ import annotations

import json
from typing import Any

from qa_core.cache.catalog import open_redis

COMMERCE_READ_MODEL_PREFIX = "commerce:order"
COMMERCE_IDEMPOTENCY_PREFIX = "idem:commerce"


def commerce_read_model_key(workspace_id: int, order_id: int) -> str:
    """Return the Redis key for one order read model."""

    return f"{COMMERCE_READ_MODEL_PREFIX}:{workspace_id}:{order_id}"


def commerce_read_model_pattern(workspace_id: int) -> str:
    """Return the read-model match pattern for one workspace."""

    return f"{COMMERCE_READ_MODEL_PREFIX}:{workspace_id}:*"


def commerce_idempotency_pattern(workspace_id: int) -> str:
    """Return the commerce idempotency match pattern for one workspace."""

    return f"{COMMERCE_IDEMPOTENCY_PREFIX}:{workspace_id}:*"


def read_commerce_read_model(
    redis_url: str,
    workspace_id: int,
    order_id: int,
) -> dict[str, Any] | None:
    """Read one PostgreSQL-derived order projection from Redis."""

    client = open_redis(redis_url)
    try:
        raw = client.get(commerce_read_model_key(workspace_id, order_id))
    finally:
        client.close()
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def purge_commerce_state(
    redis_url: str,
    workspace_id: int,
    *,
    batch_size: int = 100,
) -> int:
    """Delete commerce read models and idempotency keys for one workspace."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    client = open_redis(redis_url)
    deleted = 0
    try:
        for pattern in (
            commerce_read_model_pattern(workspace_id),
            commerce_idempotency_pattern(workspace_id),
        ):
            batch: list[str] = []
            for key in client.scan_iter(match=pattern, count=batch_size):
                batch.append(str(key))
                if len(batch) >= batch_size:
                    deleted += int(client.delete(*batch))
                    batch.clear()
            if batch:
                deleted += int(client.delete(*batch))
    finally:
        client.close()
    return deleted
