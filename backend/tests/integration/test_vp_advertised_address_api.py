"""The advertised IPv4 override persists, can be cleared, and rejects bad input."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.database import _safe_execute
from backend.app.core.virtual_printer_migrations import migrate_vp_network_config

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_advertised_address_create_update_clear(async_client):
    response = await async_client.post(
        "/api/v1/virtual-printers", json={"name": "Docker", "advertised_ip": "192.168.1.40"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["advertised_ip"] == "192.168.1.40"
    vp_id = body["id"]
    assert body["bind_ip"] is None
    for value in ("192.168.1.41", "", "192.168.1.42", None):
        response = await async_client.put(f"/api/v1/virtual-printers/{vp_id}", json={"advertised_ip": value})
        assert response.status_code == 200
        assert response.json()["advertised_ip"] == (value or None)
        read = await async_client.get(f"/api/v1/virtual-printers/{vp_id}")
        assert read.json()["advertised_ip"] == (value or None)


@pytest.mark.parametrize(
    "value", ["host.local", "::1", "0.0.0.0", "224.0.0.1", "255.255.255.255", "192.168.1.40\r\nX: injected"]
)
async def test_bad_address_does_not_create_or_modify_vp(async_client, value):
    bad_create = await async_client.post("/api/v1/virtual-printers", json={"advertised_ip": value})
    assert bad_create.status_code == 422
    created = await async_client.post("/api/v1/virtual-printers", json={"advertised_ip": "192.168.1.40"})
    vp_id = created.json()["id"]
    bad_update = await async_client.put(
        f"/api/v1/virtual-printers/{vp_id}", json={"advertised_ip": value, "name": "should not persist"}
    )
    assert bad_update.status_code == 422
    read = await async_client.get(f"/api/v1/virtual-printers/{vp_id}")
    assert read.json()["advertised_ip"] == "192.168.1.40"
    assert read.json()["name"] == "PrintOps"


async def test_existing_vp_network_migration_is_idempotent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE virtual_printers (id INTEGER PRIMARY KEY, name TEXT)"))
            await connection.execute(text("INSERT INTO virtual_printers VALUES (1, 'Existing VP')"))
            await migrate_vp_network_config(connection, _safe_execute, sqlite=True)
            await migrate_vp_network_config(connection, _safe_execute, sqlite=True)
            row = (
                await connection.execute(text("SELECT name, advertised_ip, tailscale_disabled FROM virtual_printers"))
            ).one()
            assert row == ("Existing VP", None, 1)
    finally:
        await engine.dispose()
