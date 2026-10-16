"""Fixed-window budget arithmetic, including the reset the API cannot wait for."""

from __future__ import annotations

from typing import Any

import app as sut_app
import pytest
import redis


class FakeRedis:
    """Minimal Redis stand-in for the four commands the budget uses."""

    def __init__(self, *, clock: list[float] | None = None) -> None:
        self.values: dict[str, int] = {}
        self.expires_at: dict[str, float] = {}
        self.clock = clock if clock is not None else [0.0]

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key: str, seconds: int) -> bool:
        self.expires_at[key] = self.clock[0] + seconds
        return True

    def ttl(self, key: str) -> int:
        if key not in self.values:
            return -2
        if key not in self.expires_at:
            return -1
        return max(0, int(self.expires_at[key] - self.clock[0]))

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self.values.pop(key, None) is not None:
                self.expires_at.pop(key, None)
                removed += 1
        return removed

    def close(self) -> None:
        """Match the Redis client surface the budget closes after each use."""


class BrokenRedis:
    """Every command fails, as it would when Redis is down."""

    def __getattr__(self, name: str) -> Any:
        def explode(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            raise redis.ConnectionError("redis is down")

        return explode


def _budget(
    fake: Any,
    *,
    limit: int = 3,
    window: float = 60.0,
) -> sut_app.RedisFixedWindowBudget:
    return sut_app.RedisFixedWindowBudget(
        limit=limit,
        window_seconds=window,
        scope="client",
        prefix="ratelimit:test:",
        client_factory=lambda: fake,
    )


def test_budget_counts_down_and_then_refuses() -> None:
    budget = _budget(FakeRedis())

    states = [budget.consume("k") for _ in range(3)]
    refused = budget.consume("k")

    assert [state.remaining for state in states] == [2, 1, 0]
    assert not any(state.limited for state in states)
    assert refused.limited
    assert refused.scope == "client"
    assert refused.limit == 3
    assert refused.remaining == 0
    assert refused.reset_after == pytest.approx(60.0)


def test_budget_resets_when_the_window_expires() -> None:
    """The API cannot wait a full window, so the reset is proven with a clock."""

    clock = [0.0]
    fake = FakeRedis(clock=clock)
    budget = _budget(fake, limit=2, window=10.0)
    budget.consume("k")
    budget.consume("k")
    assert budget.consume("k").limited

    clock[0] = 11.0
    fake.values.pop("ratelimit:test:k")
    fake.expires_at.pop("ratelimit:test:k", None)
    after_window = budget.consume("k")

    assert not after_window.limited
    assert after_window.remaining == 1


def test_the_advertised_reset_shrinks_with_the_window() -> None:
    clock = [0.0]
    budget = _budget(FakeRedis(clock=clock), limit=1, window=30.0)
    first = budget.consume("k")

    clock[0] = 20.0
    refused = budget.consume("k")

    assert first.reset_after == 30
    assert refused.limited
    assert refused.reset_after == 10


def test_budget_keeps_keys_apart() -> None:
    budget = _budget(FakeRedis(), limit=1)

    budget.consume("first")

    assert budget.consume("first").limited
    assert not budget.consume("second").limited


def test_a_zero_limit_disables_the_bucket() -> None:
    """A limit of 0 means "no limiter", not "block everything"."""

    budget = _budget(FakeRedis(), limit=0)

    state = budget.consume("k")

    assert state.limit == 0
    assert state.remaining == 0
    assert state.reset_after == 0.0
    assert not state.limited


def test_a_redis_outage_fails_open() -> None:
    """Redis is an accelerator here too: losing it must not block writes."""

    budget = _budget(BrokenRedis(), limit=2)

    state = budget.consume("k")

    assert not state.limited
    assert state.remaining == 2
    assert state.reset_after == 0.0


def test_clear_removes_only_the_named_key() -> None:
    fake = FakeRedis()
    budget = _budget(fake, limit=1)
    budget.consume("first")
    budget.consume("second")

    removed = fake.delete("ratelimit:test:first")

    assert removed == 1
    assert not budget.consume("first").limited
    assert budget.consume("second").limited
