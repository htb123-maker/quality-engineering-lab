"""The input-hardening contract, checked without touching the SUT."""

from __future__ import annotations

import json

import app as sut_app
import pytest
from qa_core.contracts import (
    CatalogItemCreate,
    ContractValidationError,
    MemberCreate,
    validate_contract,
)
from qa_core.security import (
    CONTROL_CHARACTER_NAMES,
    HOSTILE_NAMES,
    TRAVERSAL_SLUGS,
    deeply_nested_json,
    oversized_body,
)


def test_every_illegal_slug_is_rejected_by_the_server_pattern() -> None:
    """The pattern is the single gate between a path segment and PostgreSQL."""

    for slug in TRAVERSAL_SLUGS:
        assert sut_app.WORKSPACE_SLUG_PATTERN.match(slug) is None, slug


def test_legal_slugs_still_pass_the_pattern() -> None:
    for slug in ("atlas", "orbit", "qa-ns-1a2b3c4d-case-9f8e7d6c", "a", "a1"):
        assert sut_app.WORKSPACE_SLUG_PATTERN.match(slug) is not None, slug


def test_the_declared_body_budget_is_positive_and_enforced() -> None:
    assert sut_app.MAX_REQUEST_BYTES >= 1024
    assert len(oversized_body(sut_app.MAX_REQUEST_BYTES + 1)) > sut_app.MAX_REQUEST_BYTES


def test_nested_json_builders_produce_parseable_documents() -> None:
    nested = deeply_nested_json(50)

    assert isinstance(json.loads(nested.decode()), list)
    assert len(nested) > 50


def test_hostile_names_are_distinct_and_non_empty() -> None:
    assert len(set(HOSTILE_NAMES.values())) == len(HOSTILE_NAMES)
    assert all(name for name in HOSTILE_NAMES.values())


@pytest.mark.parametrize("name", CONTROL_CHARACTER_NAMES)
def test_control_characters_never_reach_a_write_contract(name: str) -> None:
    with pytest.raises(ContractValidationError) as caught:
        validate_contract(
            CatalogItemCreate,
            {"sku": "QA11-CTRL-0001", "name": name, "price_cents": 1},
        )

    assert caught.value.violations[0].path == "$.name"


def test_membership_cannot_be_created_with_the_owner_role() -> None:
    with pytest.raises(ContractValidationError) as caught:
        validate_contract(
            MemberCreate,
            {
                "email": "escalate@example.test",
                "display_name": "Escalate",
                "role": "owner",
            },
        )

    assert caught.value.violations[0].path == "$.role"


@pytest.mark.parametrize(
    "email",
    ["no-at-sign", "two@@example.test", "user@localhost", "@example.test"],
)
def test_membership_emails_must_be_addressable(email: str) -> None:
    with pytest.raises(ContractValidationError):
        validate_contract(
            MemberCreate,
            {"email": email, "display_name": "Bad email", "role": "viewer"},
        )
