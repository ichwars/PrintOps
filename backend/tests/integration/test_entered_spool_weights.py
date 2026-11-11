"""A weighed partial spool keeps its explicit value on its first AMS sync."""

import pytest
from sqlalchemy import select

from backend.app.models.spool import Spool

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("bulk", [False, True])
@pytest.mark.parametrize("explicit,expected", [(None, True), (False, False), (True, True)])
async def test_create_protects_positive_used_weight_and_respects_explicit_lock(async_client, bulk, explicit, expected):
    spool = {"material": "PLA", "weight_used": 125}
    if explicit is not None:
        spool["weight_locked"] = explicit
    path = "/api/v1/inventory/spools" + ("/bulk" if bulk else "")
    response = await async_client.post(path, json={"spool": spool, "quantity": 2} if bulk else spool)
    assert response.status_code == 200, response.text
    rows = response.json() if bulk else [response.json()]
    assert all(row["weight_used"] == 125 and row["weight_locked"] is expected for row in rows)


async def test_csv_positive_used_weight_is_locked(async_client, db_session):
    response = await async_client.post(
        "/api/v1/inventory/spools/import",
        files={"file": ("weights.csv", b"material,color_name,rgba,weight_used\nPLA,Blue,0000FFFF,125\n", "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1
    row = (await db_session.execute(select(Spool))).scalar_one()
    assert row.weight_used == 125
    assert row.weight_locked is True


@pytest.mark.parametrize("method", ["create", "update"])
async def test_negative_used_weight_is_rejected(async_client, method):
    path = "/api/v1/inventory/spools"
    if method == "update":
        response = await async_client.post(path, json={"material": "PLA"})
        assert response.status_code == 200, response.text
        response = await async_client.patch(f"{path}/{response.json()['id']}", json={"weight_used": -1})
    else:
        response = await async_client.post(path, json={"material": "PLA", "weight_used": -1})
    assert response.status_code == 422, response.text
