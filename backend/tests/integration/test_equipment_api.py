from decimal import Decimal


async def test_equipment_crud_and_derived_costs(async_client):
    payload = {
        "equipment_type": "dryer",
        "name": "Dryer A",
        "acquisition_date": "2026-01-01",
        "acquisition_value": "400",
        "service_years": "4",
        "annual_hours": "500",
        "maintenance_rate": "0.10",
        "nominal_power_watts": "250",
    }
    created = await async_client.post("/api/v1/equipment/", json=payload)
    assert created.status_code == 201, created.text
    equipment = created.json()
    assert equipment["equipment_type"] == "dryer"
    assert equipment["hourly_rate"] == "0.220000"
    assert Decimal(equipment["residual_value"]) <= Decimal("400")

    listed = await async_client.get("/api/v1/equipment/?active_only=true")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [equipment["id"]]

    updated = await async_client.put(f"/api/v1/equipment/{equipment['id']}", json={"is_active": False})
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    active = await async_client.get("/api/v1/equipment/?active_only=true")
    assert active.json() == []

    deleted = await async_client.delete(f"/api/v1/equipment/{equipment['id']}")
    assert deleted.status_code == 204
