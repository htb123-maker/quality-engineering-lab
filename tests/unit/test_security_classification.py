"""Every new Week 11 error code must map to exactly one owner."""

from __future__ import annotations

import app as sut_app
import httpx
import pytest
from qa_core import api_errors
from qa_core.api_errors import classify_error, classify_response
from qa_core.security import SIGNIN_FAILURE_PREFIX, signin_failure_key

NEW_CODES = [
    (400, "invalid_workspace_slug", "test"),
    (403, "owner_protected", "permission"),
    (403, "role_escalation_forbidden", "permission"),
    (403, "self_modification_forbidden", "permission"),
    (404, "member_not_found", "product"),
    (409, "member_conflict", "product"),
    (413, "payload_too_large", "test"),
    (415, "unsupported_media_type", "test"),
]


@pytest.mark.parametrize(("status", "code", "category"), NEW_CODES)
def test_new_error_codes_are_classified(
    status: int,
    code: str,
    category: str,
) -> None:
    classification = classify_error(status, code)

    assert classification.category == category
    assert classification.detail
    assert classification.is_client_error


@pytest.mark.parametrize(("status", "code", "category"), NEW_CODES)
def test_new_error_codes_are_documented_in_the_taxonomy(
    status: int,
    code: str,
    category: str,
) -> None:
    """A code that falls through to the fallback would lose its owner."""

    del category
    assert (status, code) in set(api_errors._EXACT)


def test_permission_and_input_failures_point_at_different_owners() -> None:
    """The point of the taxonomy: a red run says who should look next."""

    assert classify_error(403, "owner_protected").category == "permission"
    assert classify_error(413, "payload_too_large").category == "test"
    assert classify_error(415, "unsupported_media_type").category == "test"
    assert classify_error(429, "rate_limited").category == "environment"


def test_the_sut_key_derivation_matches_the_test_mirror() -> None:
    """The throttle probe must look where the SUT writes."""

    client_id = "qa11-unit-client"
    email = "Someone@Example.test"

    server_key = sut_app._signin_failure_key(client_id, email)

    assert server_key.startswith(SIGNIN_FAILURE_PREFIX)
    assert server_key == signin_failure_key(client_id, email)
    assert signin_failure_key(client_id, email) == signin_failure_key(
        client_id,
        email.lower(),
    )


def test_classify_response_reads_the_error_code_from_the_body() -> None:
    response = httpx.Response(
        403,
        json={"error": "role_escalation_forbidden", "message": "no"},
    )

    classification = classify_response(response)

    assert classification.error_code == "role_escalation_forbidden"
    assert classification.category == "permission"
