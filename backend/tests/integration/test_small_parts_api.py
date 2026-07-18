import pytest


@pytest.mark.asyncio
async def test_small_part_api_tracks_receipt_search_and_correction(async_client):
    unit = await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    assert unit.status_code == 201
    category = await async_client.post(
        "/api/v1/small-parts/settings/categories",
        json={"name": "Gewindeeinsätze"},
    )
    assert category.status_code == 201

    created = await async_client.post(
        "/api/v1/small-parts",
        json={
            "sku": "M3-INSERT",
            "name": "M3 Gewindeeinsatz",
            "search_terms": "Messing Insert",
            "unit_code": "C62",
            "category_id": category.json()["id"],
            "location_id": None,
            "minimum_stock": "20",
            "unit_cost": "0.08",
            "is_active": True,
        },
    )
    assert created.status_code == 201
    part_id = created.json()["id"]

    receipt_payload = {
        "entry_kind": "receipt",
        "quantity": "100",
        "reason": "Purchase",
        "idempotency_key": "receipt-M3-20260718",
    }
    receipt = await async_client.post(f"/api/v1/small-parts/{part_id}/ledger", json=receipt_payload)
    duplicate = await async_client.post(f"/api/v1/small-parts/{part_id}/ledger", json=receipt_payload)
    assert receipt.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == receipt.json()["id"]

    detail = (await async_client.get(f"/api/v1/small-parts/{part_id}")).json()
    assert detail["balance"] == {
        "physical": "100.000000",
        "reserved": "0.000000",
        "available": "100.000000",
        "is_low_stock": False,
    }
    search = await async_client.get("/api/v1/small-parts/search", params={"q": "gewindeeinsätze"})
    assert search.status_code == 200
    assert [(item["sku"], item["available"]) for item in search.json()] == [("M3-INSERT", "100.000000")]

    overdraw = await async_client.post(
        f"/api/v1/small-parts/{part_id}/ledger",
        json={
            "entry_kind": "correction",
            "quantity": "-101",
            "reason": "Inventory count",
            "idempotency_key": "correction-M3-overdraw",
        },
    )
    assert overdraw.status_code == 409
    assert overdraw.json()["detail"]["code"] == "insufficient_stock"


@pytest.mark.asyncio
async def test_inactive_small_parts_are_excluded_from_search_by_default(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    created = await async_client.post(
        "/api/v1/small-parts",
        json={
            "sku": "OLD-PART",
            "name": "Inaktives Kleinteil",
            "unit_code": "C62",
            "minimum_stock": "0",
            "unit_cost": "0",
            "is_active": False,
        },
    )
    assert created.status_code == 201

    search = await async_client.get("/api/v1/small-parts/search", params={"q": "OLD"})

    assert search.status_code == 200
    assert search.json() == []
