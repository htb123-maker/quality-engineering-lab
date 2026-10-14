"""Boundary-value tests for the catalog write contract."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import httpx
import pytest
from qa_core.config.settings import Settings
from qa_core.contracts import ValidationErrorResponse, validate_contract
from qa_core.data_factories import CatalogApiFactory, items_path
from qa_core.http import HttpClient

from tests.api.conftest import attach_json


def _validation(response: httpx.Response) -> ValidationErrorResponse:
    return validate_contract(ValidationErrorResponse, response.json())


def _field_paths(validation: ValidationErrorResponse) -> list[str]:
    return [field.field for field in validation.fields]


@pytest.mark.api
def test_zero_price_is_allowed_at_the_lower_boundary(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.create(price_cents=0)

    assert response.status_code == 201
    assert response.json()["price_cents"] == 0
    attach_json("Lower-boundary item", response.json())


@pytest.mark.api
@pytest.mark.parametrize("price_cents", [-1, 100_000_001])
def test_out_of_range_price_is_rejected(
    catalog_items: CatalogApiFactory,
    price_cents: int,
) -> None:
    response = catalog_items.create(price_cents=price_cents)

    assert response.status_code == 422
    validation = _validation(response)
    assert validation.error == "validation_failed"
    assert _field_paths(validation) == ["$.price_cents"]
    attach_json("Out-of-range price", validation.model_dump(mode="json"))


@pytest.mark.api
def test_blank_name_is_rejected(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.create(name="")

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.name"]


@pytest.mark.api
def test_name_at_max_length_is_allowed(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.create(name="A" * 120)

    assert response.status_code == 201
    assert len(response.json()["name"]) == 120


@pytest.mark.api
def test_name_over_max_length_is_rejected(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.create(name="A" * 121)

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.name"]


@pytest.mark.api
@pytest.mark.parametrize("sku", ["QA", "qa7w-lower", "QA7W BAD!"])
def test_invalid_sku_is_rejected(
    catalog_items: CatalogApiFactory,
    sku: str,
) -> None:
    response = catalog_items.create(sku=sku)

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.sku"]
    attach_json("Invalid SKU", _validation(response).model_dump(mode="json"))


@pytest.mark.api
def test_sku_over_max_length_is_rejected(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.create(sku="Q" * 65)

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.sku"]


@pytest.mark.api
def test_missing_required_field_reports_field_path(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.auth.post(
        items_path(catalog_items.workspace_slug),
        json={"name": "No SKU", "price_cents": 100},
        headers={"X-QA-Client-Id": catalog_items.client_id},
    )

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.sku"]


@pytest.mark.api
def test_unknown_field_is_rejected(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.auth.post(
        items_path(catalog_items.workspace_slug),
        json={
            "sku": catalog_items.new_sku("EXTRA"),
            "name": "Extra field",
            "price_cents": 100,
            "unexpected": True,
        },
        headers={"X-QA-Client-Id": catalog_items.client_id},
    )

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.unexpected"]


@pytest.mark.api
def test_duplicate_sku_is_a_conflict(
    catalog_items: CatalogApiFactory,
) -> None:
    sku = catalog_items.new_sku("DUP")
    first = catalog_items.create(sku=sku)
    second = catalog_items.create(sku=sku)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"] == "sku_conflict"
    attach_json("Duplicate SKU conflict", second.json())


@pytest.mark.api
def test_workspace_slug_is_case_sensitive(
    sut_api_url: str,
    settings: Settings,
) -> None:
    del sut_api_url

    with HttpClient.from_settings(settings) as client:
        response = client.get("/api/v1/workspaces/ATLAS/catalog")

    assert response.status_code == 404
    assert response.json()["error"] == "workspace_not_found"
    attach_json("Case-sensitive slug", response.json())


@pytest.mark.api
def test_sku_at_minimum_length_is_allowed(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.create(sku="QAB")

    assert response.status_code == 201
    assert response.json()["sku"] == "QAB"
    attach_json("Minimum-length SKU", response.json())


@pytest.mark.api
def test_sku_at_maximum_length_is_allowed(
    catalog_items: CatalogApiFactory,
) -> None:
    sku = f"QA8-{'A' * 60}"
    assert len(sku) == 64

    response = catalog_items.create(sku=sku)

    assert response.status_code == 201
    assert response.json()["sku"] == sku


@pytest.mark.api
def test_name_at_minimum_length_is_allowed(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.create(name="A")

    assert response.status_code == 201
    assert response.json()["name"] == "A"


@pytest.mark.api
def test_price_at_upper_boundary_is_allowed(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.create(price_cents=100_000_000)

    assert response.status_code == 201
    assert response.json()["price_cents"] == 100_000_000
    attach_json("Upper-boundary price", response.json())


@pytest.mark.api
def test_missing_name_reports_the_name_field(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.auth.post(
        items_path(catalog_items.workspace_slug),
        json={"sku": catalog_items.new_sku("NONAME"), "price_cents": 100},
        headers={"X-QA-Client-Id": catalog_items.client_id},
    )

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.name"]


@pytest.mark.api
def test_missing_price_reports_the_price_field(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.auth.post(
        items_path(catalog_items.workspace_slug),
        json={"sku": catalog_items.new_sku("NOPRICE"), "name": "No price"},
        headers={"X-QA-Client-Id": catalog_items.client_id},
    )

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.price_cents"]


@pytest.mark.api
@pytest.mark.parametrize("price_cents", ["free", None, [1000]])
def test_non_integer_price_is_rejected(
    catalog_items: CatalogApiFactory,
    price_cents: object,
) -> None:
    response = catalog_items.auth.post(
        items_path(catalog_items.workspace_slug),
        json={
            "sku": catalog_items.new_sku("BADPRICE"),
            "name": "Bad price type",
            "price_cents": price_cents,
        },
        headers={"X-QA-Client-Id": catalog_items.client_id},
    )

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.price_cents"]
    attach_json("Non-integer price", _validation(response).model_dump(mode="json"))


@pytest.mark.api
def test_non_string_sku_is_rejected(
    catalog_items: CatalogApiFactory,
) -> None:
    response = catalog_items.auth.post(
        items_path(catalog_items.workspace_slug),
        json={"sku": ["QA8", "LIST"], "name": "Bad sku type", "price_cents": 100},
        headers={"X-QA-Client-Id": catalog_items.client_id},
    )

    assert response.status_code == 422
    assert _field_paths(_validation(response)) == ["$.sku"]
