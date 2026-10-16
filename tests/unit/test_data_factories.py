"""Unit tests for slug, SKU, and path helpers in the data factories."""

from __future__ import annotations

import re
from typing import cast

import pytest
from qa_core.auth import AuthClient
from qa_core.data_factories import CatalogApiFactory, NamespaceFactory, item_path, items_path
from qa_core.db import DatabaseClient


def _factory(prefix: str = "qa-ns-", run_token: str = "run1") -> NamespaceFactory:
    return NamespaceFactory(
        cast(DatabaseClient, None),
        prefix=prefix,
        run_token=run_token,
    )


def test_new_slug_uses_prefix_run_token_and_tag() -> None:
    slug = _factory().new_slug("Case One")

    assert slug.startswith("qa-ns-run1-case-one-")
    assert len(slug) <= 60


def test_new_slug_is_unique_across_calls() -> None:
    factory = _factory()

    slugs = {factory.new_slug("dup") for _ in range(25)}

    assert len(slugs) == 25


def test_new_slug_normalizes_unsafe_tag_characters() -> None:
    slug = _factory().new_slug("Week 8 / round #2")

    assert "/" not in slug
    assert "#" not in slug
    assert " " not in slug
    assert re.fullmatch(r"[a-z0-9.:-]+", slug)


def test_blank_tag_is_rejected() -> None:
    with pytest.raises(ValueError, match="tag must contain at least one letter or digit"):
        _factory().new_slug("///")


def test_new_item_sku_matches_the_contract_pattern() -> None:
    sku = _factory().new_item_sku("seed 1")

    assert re.fullmatch(r"^[A-Z0-9][A-Z0-9-]*$", sku)
    assert 3 <= len(sku) <= 64
    assert sku.startswith("QA8-SEED-1-")


def test_new_item_sku_is_unique_across_calls() -> None:
    factory = _factory()

    skus = {factory.new_item_sku() for _ in range(25)}

    assert len(skus) == 25


def test_factory_rejects_a_seed_prefix() -> None:
    with pytest.raises(ValueError, match="must not be empty or seed data"):
        _factory(prefix="")

    with pytest.raises(ValueError, match="must not be empty or seed data"):
        _factory(prefix="LAB-")


def test_run_prefix_excludes_other_runs() -> None:
    factory = _factory(run_token="abc123")

    assert factory.run_prefix() == "qa-ns-abc123-"
    assert factory.run_prefix("other") == "qa-ns-other-"


def test_catalog_paths_include_the_workspace_slug() -> None:
    assert items_path("qa-ns-1") == "/api/v1/workspaces/qa-ns-1/catalog/items"
    assert (
        item_path(42, "qa-ns-1")
        == "/api/v1/workspaces/qa-ns-1/catalog/items/42"
    )


def test_catalog_factory_sku_is_unique_and_valid() -> None:
    factory = CatalogApiFactory(
        auth=cast(AuthClient, None),
        workspace_slug="qa-ns-1",
        client_id="client-1",
    )

    skus = {factory.new_sku("tag one") for _ in range(10)}

    assert len(skus) == 10
    assert all(re.fullmatch(r"^[A-Z0-9][A-Z0-9-]*$", sku) for sku in skus)
    assert all(sku.startswith("QA8-TAGONE-") for sku in skus)
