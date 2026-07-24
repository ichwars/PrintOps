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
