"""The opt-in keep-warm contract shares the existing protected settings route."""

import pytest


@pytest.mark.asyncio
async def test_keep_warm_defaults_and_typed_round_trip(async_client):
    response = await async_client.get("/api/v1/settings/")
    assert response.status_code == 200
    assert response.json()["queue_keep_bed_warm"] is False
    assert response.json()["queue_keep_warm_max_minutes"] == 10
    response = await async_client.put(
        "/api/v1/settings/",
        json={
            "queue_keep_bed_warm": True,
            "queue_keep_warm_max_minutes": 15,
        },
    )
    assert response.status_code == 200
    response = await async_client.get("/api/v1/settings/")
    assert response.json()["queue_keep_bed_warm"] is True
    assert response.json()["queue_keep_warm_max_minutes"] == 15


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [0, 31])
async def test_keep_warm_duration_outside_safe_contract_is_rejected(async_client, minutes):
    response = await async_client.put("/api/v1/settings/", json={"queue_keep_warm_max_minutes": minutes})
    assert response.status_code == 422
