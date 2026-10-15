"""The test-side cache inspectors must agree with the SUT key layout."""

from __future__ import annotations

from pathlib import Path

import app as sut_app
from qa_core.cache import (
    cache_stats_key,
    catalog_absent_cache_key,
    catalog_cache_key,
    catalog_cache_pattern,
)

SLUG = "qa-ns-run1-case-00000000"


def test_sut_and_test_helpers_derive_the_same_cache_keys() -> None:
    """A test reads the real Redis state, so both sides must build one key name."""

    assert sut_app.catalog_cache_key(SLUG) == catalog_cache_key(SLUG)
    assert sut_app.catalog_absent_cache_key(SLUG) == catalog_absent_cache_key(SLUG)
    assert sut_app.cache_stats_key(SLUG, "hit") == cache_stats_key(SLUG, "hit")
    assert catalog_cache_pattern(SLUG).startswith(catalog_cache_key(SLUG))


def test_cache_variable_names_are_documented_for_the_compose_sut() -> None:
    """The container only receives the knobs the Compose file passes through."""

    project_root = Path(__file__).resolve().parents[2]
    compose = (project_root / "apps" / "compose" / "compose.yaml").read_text(
        encoding="utf-8"
    )

    for name in (
        "QA_CATALOG_CACHE_TTL_SECONDS",
        "QA_CATALOG_CACHE_NEGATIVE_TTL_SECONDS",
        "QA_JOB_TTL_SECONDS",
        "QA_JOB_WORKER_ENABLED",
        "QA_JOB_WORKER_POLL_SECONDS",
        "QA_WS_SUBSCRIBER_QUEUE_SIZE",
    ):
        assert name in compose, name
