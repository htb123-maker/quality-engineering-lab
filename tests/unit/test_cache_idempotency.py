"""Unit tests for Redis idempotency cleanup helpers."""

from __future__ import annotations

import pytest
from qa_core.cache import IDEMPOTENCY_KEY_PREFIX, idempotency_key_pattern, purge_idempotency_keys


def test_key_pattern_targets_one_workspace() -> None:
    assert idempotency_key_pattern(7) == "idem:7:*"
    assert IDEMPOTENCY_KEY_PREFIX == "idem:"


def test_key_pattern_is_namespaced_by_workspace() -> None:
    assert idempotency_key_pattern(1) != idempotency_key_pattern(11)
    assert idempotency_key_pattern(11).startswith("idem:11:")


def test_purge_rejects_an_invalid_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size must be at least 1"):
        purge_idempotency_keys("redis://127.0.0.1:1/0", 1, batch_size=0)
