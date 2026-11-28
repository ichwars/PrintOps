from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

BASE_URL = "/api/v1/inventory/number-sequences"


@pytest.mark.asyncio
async def test_warehouse_number_sequence_can_be_created_and_listed(async_client: AsyncClient):
    listed = await async_client.get(BASE_URL)

    assert listed.status_code == 200, listed.text
    assert listed.json() == []

    created = await async_client.post(
        BASE_URL,
        json={
            "key": "material",
            "prefix": "MAT",
            "pattern": "{PREFIX}-{#####}",
            "next_value": 1001,
            "reset_policy": "none",
        },
    )

    assert created.status_code == 201, created.text
    assert {
        "key": "material",
        "prefix": "MAT",
        "pattern": "{PREFIX}-{#####}",
        "next_value": 1001,
        "reset_policy": "none",
        "current_period": None,
        "version": 1,
    }.items() <= created.json().items()

    listed_again = await async_client.get(BASE_URL)
    assert [item["key"] for item in listed_again.json()] == ["material"]


@pytest.mark.asyncio
async def test_warehouse_number_sequence_update_validates_pattern_and_version(async_client: AsyncClient):
    created = await async_client.post(
        BASE_URL,
        json={
            "key": "goods_receipt",
            "prefix": "WE",
            "pattern": "{PREFIX}-{YYYY}-{#####}",
            "next_value": 1,
            "reset_policy": "yearly",
        },
    )
    assert created.status_code == 201, created.text
    sequence = created.json()

    updated = await async_client.put(
        f"{BASE_URL}/{sequence['id']}",
        json={
            "prefix": "WE",
            "pattern": "{PREFIX}-{YY}-{####}",
            "next_value": 101,
            "reset_policy": "yearly",
            "version": sequence["version"],
        },
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["next_value"] == 101
    assert updated.json()["version"] == sequence["version"] + 1

    stale = await async_client.put(
        f"{BASE_URL}/{sequence['id']}",
        json={
            "prefix": "ALT",
            "pattern": "{PREFIX}-{#####}",
            "next_value": 1,
            "reset_policy": "none",
            "version": sequence["version"],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    invalid = await async_client.post(
        BASE_URL,
        json={
            "key": "purchase_order",
            "prefix": "BE",
            "pattern": "{PREFIX}-{UNKNOWN}-{####}",
            "next_value": 1,
            "reset_policy": "yearly",
        },
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_yearly_warehouse_number_sequence_requires_year_token(async_client: AsyncClient):
    created = await async_client.post(
        BASE_URL,
        json={
            "key": "purchase_order",
            "prefix": "BE",
            "pattern": "{PREFIX}-{#####}",
            "next_value": 1,
            "reset_policy": "yearly",
        },
    )

    assert created.status_code == 422


async def _next_values(client: AsyncClient) -> dict[str, int]:
    response = await client.get(BASE_URL)
    assert response.status_code == 200, response.text
    return {item["key"]: item["next_value"] for item in response.json()}


@pytest.mark.asyncio
async def test_new_spools_get_distinct_numbers(async_client: AsyncClient):
    payload = {"material": "PLA", "color_name": "Numbering test"}
    created = await async_client.post("/api/v1/inventory/spools", json=payload)
    assert created.status_code == 200, created.text
    assert created.json().get("spool_number") == "SP-00001"
    assert (await _next_values(async_client))["spool"] == 2

    bulk = await async_client.post("/api/v1/inventory/spools/bulk", json={"spool": payload, "quantity": 2})
    assert bulk.status_code == 200, bulk.text
    assert [item["spool_number"] for item in bulk.json()] == ["SP-00002", "SP-00003"]
    assert (await _next_values(async_client))["spool"] == 4
    stored = await async_client.get(f"/api/v1/inventory/spools/{created.json()['id']}")
    assert stored.json()["spool_number"] == "SP-00001"


@pytest.mark.asyncio
async def test_lowered_spool_counter_skips_more_than_ten_used_numbers(async_client: AsyncClient):
    spool_url = "/api/v1/inventory/spools"
    payload = {"material": "PLA", "color_name": "Numbering test"}
    bulk = await async_client.post(f"{spool_url}/bulk", json={"spool": payload, "quantity": 12})
    assert bulk.status_code == 200, bulk.text
    sequence = next(item for item in (await async_client.get(BASE_URL)).json() if item["key"] == "spool")
    reset = await async_client.put(
        f"{BASE_URL}/{sequence['id']}",
        json={
            **{key: sequence[key] for key in ("prefix", "pattern", "reset_policy", "version")},
            "next_value": 1,
        },
    )
    assert reset.status_code == 200, reset.text

    created = await async_client.post(spool_url, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["spool_number"] == "SP-00013"
    assert (await _next_values(async_client))["spool"] == 14


async def _part(client: AsyncClient) -> int:
    await client.post("/api/v1/small-parts/settings/units", json={"code": "C62", "label": "Stück"})
    response = await client.post(
        "/api/v1/small-parts",
        json={
            "sku": "TEST-NUMBERING",
            "name": "Numbering test",
            "unit_code": "C62",
            "minimum_stock": "5",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_receipt_replay_keeps_one_receipt_number(async_client: AsyncClient):
    part_id = await _part(async_client)
    path = f"/api/v1/small-parts/{part_id}/ledger"
    command = {"entry_kind": "receipt", "quantity": "1", "reason": "Test", "idempotency_key": "test-receipt-number"}
    response = await async_client.post(path, json=command)
    assert response.status_code == 201, response.text
    assert response.json().get("receipt_number") == f"WE-{date.today().year}-00001"
    replay = await async_client.post(path, json=command)
    assert replay.json() == response.json()
    assert (await _next_values(async_client))["goods_receipt"] == 2


@pytest.mark.asyncio
async def test_shopping_item_creates_one_numbered_purchase_order(async_client: AsyncClient):
    part_id = await _part(async_client)
    added = await async_client.put(f"/api/v1/warehouse-shopping-list/material/{part_id}")
    assert added.status_code == 200, added.text
    path = f"/api/v1/warehouse-shopping-list/{added.json()['id']}/purchase-order"
    created = await async_client.post(path)
    assert created.status_code == 201, created.text
    assert created.json()["number"] == f"BE-{date.today().year}-00001"
    second = await async_client.post(path)
    assert second.json() == created.json()
    assert (await _next_values(async_client))["purchase_order"] == 2
    listed = await async_client.get("/api/v1/warehouse-purchase-orders")
    assert listed.json() == [created.json()]


@pytest.mark.asyncio
async def test_receive_purchase_order_in_parts_without_overbooking(async_client: AsyncClient):
    part_id = await _part(async_client)
    added = await async_client.put(f"/api/v1/warehouse-shopping-list/material/{part_id}")
    created = await async_client.post(f"/api/v1/warehouse-shopping-list/{added.json()['id']}/purchase-order")
    assert created.status_code == 201, created.text
    order = created.json()
    path = f"/api/v1/warehouse-purchase-orders/{order['id']}/receipts"

    command = {"quantity": "2", "idempotency_key": "receive-order-partial"}
    partial = await async_client.post(path, json=command)
    assert partial.status_code == 201, partial.text
    data = partial.json()
    assert data["receipt_number"] == f"WE-{date.today().year}-00001"
    assert Decimal(data["order"]["received_quantity"]) == 2
    assert Decimal(data["order"]["open_quantity"]) == 3
    shopping = await async_client.get("/api/v1/warehouse-shopping-list")
    assert [item["id"] for item in shopping.json()] == [added.json()["id"]]
    assert Decimal((await async_client.get(f"/api/v1/small-parts/{part_id}")).json()["balance"]["physical"]) == 2

    duplicate = await async_client.post(path, json=command)
    assert duplicate.json() == data
    over = await async_client.post(path, json={"quantity": "4", "idempotency_key": "receive-order-overbook"})
    assert over.status_code == 409
    assert (await _next_values(async_client))["goods_receipt"] == 2

    final = await async_client.post(path, json={"quantity": "3", "idempotency_key": "receive-order-complete"})
    assert final.status_code == 201, final.text
    assert Decimal(final.json()["order"]["open_quantity"]) == 0
    assert final.json()["order"]["shopping_item_id"] is None
    assert (await async_client.get("/api/v1/warehouse-shopping-list")).json() == []
    assert (await async_client.get("/api/v1/warehouse-purchase-orders")).json() == [final.json()["order"]]

    history = await async_client.get(path)
    assert history.status_code == 200, history.text
    assert [(row["receipt_number"], Decimal(row["quantity"])) for row in history.json()] == [
        (data["receipt_number"], Decimal("2")),
        (final.json()["receipt_number"], Decimal("3")),
    ]
    replay = await async_client.post(path, json={"quantity": "3", "idempotency_key": "receive-order-complete"})
    assert replay.json() == final.json()
    assert Decimal((await async_client.get(f"/api/v1/small-parts/{part_id}")).json()["balance"]["physical"]) == 5
    assert (await _next_values(async_client))["goods_receipt"] == 3
    assert (await _next_values(async_client))["purchase_order"] == 2
