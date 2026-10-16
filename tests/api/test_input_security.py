"""Input hardening: oversized bodies, wrong media types, and hostile text.

Three different failures deserve three different answers, and the tests pin the
boundary: 400 means "the body was unreadable", 413 means "the body was too big",
415 means "the media type is not read here", and 422 means "the JSON was fine
but a field broke a rule". Hostile *text* is a fourth case: it is stored
verbatim and never executed, escaped, or reflected into headers.
"""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import json

import allure
import httpx
import pytest
from qa_core.api_errors import classify_response
from qa_core.auth import AuthClient
from qa_core.config.settings import Settings
from qa_core.contracts import CatalogItemCreate, ContractValidationError, validate_contract
from qa_core.data_factories import CatalogApiFactory, item_path, items_path
from qa_core.http import HttpClient
from qa_core.resource_pools import NamespaceLease
from qa_core.security import (
    CONTROL_CHARACTER_NAMES,
    HOSTILE_NAMES,
    TRAVERSAL_SLUGS,
    deeply_nested_json,
    oversized_body,
)

from tests.api.conftest import attach_json, members_path, unique_client_id


def _error_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        raw = payload.get("error")
        if isinstance(raw, str):
            return raw
    return None


def _post_items(
    auth: AuthClient,
    namespace: NamespaceLease,
    *,
    content: bytes,
    content_type: str,
) -> httpx.Response:
    return auth.post(
        items_path(namespace.slug),
        content=content,
        headers={
            "Content-Type": content_type,
            "X-QA-Client-Id": unique_client_id("input"),
        },
    )


@allure.epic("Quality Engineering Lab")
@allure.feature("Input security")
@allure.story("Body budget")
@pytest.mark.api
def test_oversized_body_is_rejected_with_413(
    sut_api_url: str,
    settings: Settings,
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    del sut_api_url

    payload = oversized_body(settings.max_request_bytes + 4096)
    response = _post_items(
        owner_auth,
        namespace,
        content=payload,
        content_type="application/json",
    )

    assert len(payload) > settings.max_request_bytes
    assert response.status_code == 413
    assert _error_code(response) == "payload_too_large"
    assert classify_response(response).category == "test"
    attach_json(
        "Oversized body",
        {
            "sent_bytes": len(payload),
            "limit": settings.max_request_bytes,
            "status": response.status_code,
            "body": response.json(),
        },
    )


@allure.feature("Input security")
@allure.story("Body budget")
@pytest.mark.api
def test_the_sut_stays_healthy_after_an_oversized_body(
    sut_api_url: str,
    settings: Settings,
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    """A rejected giant body must not leave the connection or server broken."""

    _post_items(
        owner_auth,
        namespace,
        content=oversized_body(settings.max_request_bytes * 2),
        content_type="application/json",
    )

    with HttpClient.from_settings(settings) as client:
        health = client.get("/health/ready")
    accepted = owner_auth.post(
        items_path(namespace.slug),
        json={"sku": "QA11-AFTER-0001", "name": "after", "price_cents": 100},
        headers={"X-QA-Client-Id": unique_client_id("after-big")},
    )

    assert sut_api_url
    assert health.status_code == 200
    assert accepted.status_code == 201


@allure.feature("Input security")
@allure.story("Media type")
@pytest.mark.api
def test_unsupported_media_type_is_rejected_with_415(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    response = _post_items(
        owner_auth,
        namespace,
        content=b"sku=QA11-MEDIA-0001",
        content_type="text/plain",
    )

    assert response.status_code == 415
    assert _error_code(response) == "unsupported_media_type"
    attach_json("Unsupported media type", response.json())


@allure.feature("Input security")
@allure.story("Media type")
@pytest.mark.api
def test_the_oauth_endpoint_keeps_its_own_error_shape(
    sut_api_url: str,
    settings: Settings,
) -> None:
    """RFC 6749 keeps 400 invalid_request for the token endpoint."""

    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.post(
            settings.auth_token_path,
            content=b"grant_type=password",
            headers={"Content-Type": "application/xml"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    assert "error_description" in response.json()


@allure.feature("Input security")
@allure.story("Malformed bodies")
@pytest.mark.api
@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"{not-json", "application/json"),
        (b'["not", "an", "object"]', "application/json"),
        (b"\xff\xfe\x00\x00", "application/json"),
        (b'{"sku": "\xff\xfe"}', "application/json"),
    ],
)
def test_unreadable_bodies_are_400_not_500(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
    content: bytes,
    content_type: str,
) -> None:
    response = _post_items(
        owner_auth,
        namespace,
        content=content,
        content_type=content_type,
    )

    assert response.status_code == 400
    assert _error_code(response) == "invalid_request"
    attach_json("Unreadable body", {"content": repr(content), "body": response.json()})


@allure.feature("Input security")
@allure.story("Malformed bodies")
@pytest.mark.api
def test_deeply_nested_json_is_a_client_error_not_a_crash(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    response = _post_items(
        owner_auth,
        namespace,
        content=deeply_nested_json(5000),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _error_code(response) == "invalid_request"
    attach_json("Nested JSON", {"status": response.status_code})


@allure.feature("Input security")
@allure.story("Control characters")
@pytest.mark.api
@pytest.mark.parametrize("name", CONTROL_CHARACTER_NAMES)
def test_control_characters_in_text_fields_are_rejected(
    catalog_items: CatalogApiFactory,
    name: str,
) -> None:
    response = catalog_items.create(name=name)

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_failed"
    assert [field["field"] for field in body["fields"]] == ["$.name"]
    attach_json("Control character", {"name": repr(name), "body": body})


@allure.feature("Input security")
@allure.story("Control characters")
@pytest.mark.api
def test_the_contract_refuses_control_characters_before_the_server_sees_them() -> None:
    """The shared model is the first gate, and it runs inside the test too."""

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(
            CatalogItemCreate,
            {"sku": "QA11-CTRL-0001", "name": "line\nbreak", "price_cents": 1},
        )

    assert caught.value.violations[0].path == "$.name"


@allure.feature("Input security")
@allure.story("Path handling")
@pytest.mark.api
@pytest.mark.parametrize("slug", TRAVERSAL_SLUGS)
def test_illegal_workspace_slugs_never_reach_the_database(
    owner_auth: AuthClient,
    slug: str,
) -> None:
    response = owner_auth.get(members_path(slug))

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_workspace_slug"
    assert "root:" not in response.text
    attach_json("Illegal slug", {"slug": slug, "body": response.json()})


@allure.feature("Input security")
@allure.story("Path handling")
@pytest.mark.api
def test_a_raw_traversal_path_never_succeeds(
    owner_auth: AuthClient,
    namespace: NamespaceLease,
) -> None:
    response = owner_auth.get(
        f"/api/v1/workspaces/../{namespace.slug}/members",
    )

    assert response.status_code in {400, 403, 404}
    assert "root:" not in response.text
    attach_json(
        "Raw traversal",
        {"status": response.status_code, "body": response.text[:200]},
    )


@allure.feature("Input security")
@allure.story("Hostile text")
@pytest.mark.api
@pytest.mark.parametrize("label", sorted(HOSTILE_NAMES))
def test_hostile_text_is_stored_verbatim_and_never_reflected(
    owner_auth: AuthClient,
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
    label: str,
) -> None:
    """Injection payloads are data: they are stored, returned, and not executed."""

    name = HOSTILE_NAMES[label]
    created = catalog_items.create(name=name)

    assert created.status_code == 201
    item_id = int(created.json()["id"])
    fetched = owner_auth.get(item_path(item_id, namespace.slug))

    assert fetched.status_code == 200
    assert fetched.json()["name"] == name
    joined_headers = json.dumps(dict(fetched.headers))
    assert "alert(" not in joined_headers
    assert "DROP TABLE" not in joined_headers
    attach_json(
        "Hostile text",
        {"label": label, "name": name, "stored": fetched.json()["name"]},
    )


@allure.feature("Input security")
@allure.story("Hostile text")
@pytest.mark.api
def test_the_catalog_still_answers_after_injection_payloads(
    owner_auth: AuthClient,
    catalog_items: CatalogApiFactory,
    namespace: NamespaceLease,
) -> None:
    for name in HOSTILE_NAMES.values():
        created = catalog_items.create(name=name)
        assert created.status_code == 201

    catalog = owner_auth.get(f"/api/v1/workspaces/{namespace.slug}/catalog")
    listed_names = {item["name"] for item in catalog.json()["items"]}

    assert catalog.status_code == 200
    assert set(HOSTILE_NAMES.values()).issubset(listed_names)
    attach_json(
        "Catalog after injection",
        {"count": catalog.json()["count"], "names": sorted(listed_names)},
    )
