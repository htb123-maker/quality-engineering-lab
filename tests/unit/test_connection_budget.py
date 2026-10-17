"""Connection budgets keep parallel API request threads below a hard ceiling."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import app as sut_app
import psycopg
import pytest


@pytest.mark.unit
def test_connection_budget_tracks_peak_and_rejects_exhausted_waiters() -> None:
    budget = sut_app.ConnectionBudget(capacity=2, wait_seconds=0.2)
    entered = threading.Barrier(3)
    release = threading.Event()

    def hold_slot() -> None:
        with budget.slot():
            entered.wait(timeout=2)
            release.wait(timeout=2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(hold_slot) for _ in range(2)]
        entered.wait(timeout=2)

        snapshot = budget.snapshot
        assert snapshot.active == 2
        assert snapshot.peak == 2
        assert snapshot.capacity == 2

        exhausted = sut_app.ConnectionBudget(capacity=1, wait_seconds=0.01)
        with exhausted.slot():
            with pytest.raises(sut_app.ConnectionBudgetExhausted):
                with exhausted.slot():
                    pass

        release.set()
        for future in futures:
            future.result(timeout=2)

    assert budget.snapshot.active == 0
    assert budget.snapshot.peak == 2


@pytest.mark.unit
def test_postgres_helper_acquires_and_releases_the_global_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            observed.append("enter")
            return self

        def __exit__(self, *args: object) -> None:
            observed.append("exit")

    def fake_connect(*args: object, **kwargs: object) -> FakeConnection:
        assert args == (sut_app.POSTGRES_DSN,)
        assert kwargs == {"connect_timeout": 2}
        return FakeConnection()

    budget = sut_app.ConnectionBudget(capacity=1, wait_seconds=0.2)
    monkeypatch.setattr(sut_app, "_POSTGRES_BUDGET", budget)
    monkeypatch.setattr(psycopg, "connect", fake_connect)

    with sut_app._postgres_connection() as connection:
        assert isinstance(connection, FakeConnection)
        assert budget.snapshot.active == 1

    assert observed == ["enter", "exit"]
    assert budget.snapshot.active == 0
