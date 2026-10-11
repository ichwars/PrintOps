"""Environmental telemetry remains independent of storage and print authority."""

from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.app.core.auth import create_access_token
from backend.app.models.group import Group
from backend.app.models.location import Location
from backend.app.models.printer_ha_sensor import PrinterHASensor
from backend.app.models.storage_ha_sensor import StorageHASensor
from backend.app.models.user import User
from backend.app.services.ha_sensor_manager import HASensorManager
from backend.app.services.location_service import assign_location_name
from backend.app.services.storage_ha_sensors import StorageHASensorManager, storage_ha_sensor_manager
from backend.app.utils.local_time import utcnow_naive

BASE = "/api/v1/storage-ha-sensors"
HUMIDITY = {"name": "Humidity", "entity_id": "sensor.drybox_humidity", "device_class": "humidity", "unit": "%"}


@pytest.fixture(autouse=True)
def no_network():
    with patch.object(storage_ha_sensor_manager, "refresh_one", AsyncMock()):
        yield
    storage_ha_sensor_manager._readings.clear()
    storage_ha_sensor_manager._last_alerting.clear()


async def location(db):
    row = Location()
    assign_location_name(row, "Existing dry box")
    db.add(row)
    await db.commit()
    return row


async def bind(client, row, **changes):
    return await client.post(f"{BASE}/", json={**HUMIDITY, "location_id": row.id, **changes})


@pytest.mark.asyncio
async def test_binding_crud_duplicate_and_existing_location_only(async_client, db_session):
    row = await location(db_session)
    missing = await async_client.post(f"{BASE}/", json={**HUMIDITY, "location_id": 9999})
    assert missing.status_code == 404
    created = await bind(async_client, row)
    assert created.status_code == 201
    assert created.json()["notify_on_alert"] is False
    assert "block_print" not in created.json()
    assert (await bind(async_client, row)).status_code == 409
    sensor_id = created.json()["id"]
    updated = await async_client.patch(f"{BASE}/{sensor_id}", json={"alert_above": 50, "notify_on_alert": True})
    assert updated.status_code == 200
    invalid = await async_client.patch(f"{BASE}/{sensor_id}", json={"alert_above": None})
    assert invalid.status_code == 422
    assert (await async_client.get(f"{BASE}/?location_id={row.id}")).json()[0]["id"] == sensor_id
    assert (await async_client.delete(f"{BASE}/{sensor_id}")).status_code == 204
    assert (await async_client.get(f"{BASE}/")).json() == []
    assert (await db_session.get(Location, row.id)).name == "Existing dry box"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"entity_id": "switch.heater"},
        {"entity_id": "sensor.invalid/path"},
        {"unit": "°C"},
        {"device_class": "power"},
        {"block_print": True},
        {"notify_on_alert": True},
        {"alert_above": 20, "alert_below": 30},
        {"name": "   "},
        {"alert_above": "NaN"},
    ],
)
async def test_binding_rejects_invalid_or_control_configuration(async_client, db_session, changes):
    row = await location(db_session)
    assert (await bind(async_client, row, **changes)).status_code == 422


@pytest.mark.asyncio
async def test_reading_freshness_outage_and_restart(async_client, db_session):
    row = await location(db_session)
    response = await bind(async_client, row, alert_above=50)
    sensor = await db_session.get(StorageHASensor, response.json()["id"])
    assert (await async_client.get(f"{BASE}/readings")).json()[0]["status"] == "pending"
    await storage_ha_sensor_manager.apply(db_session, [sensor], {sensor.entity_id: {"state": "60"}})
    fresh = (await async_client.get(f"{BASE}/readings")).json()[0]
    assert (fresh["value"], fresh["unit"], fresh["status"], fresh["alerting"]) == (60, "%", "fresh", True)
    assert fresh["last_read_at"]
    sensor.last_read_at = utcnow_naive() - timedelta(minutes=2)
    await db_session.commit()
    stale = (await async_client.get(f"{BASE}/readings")).json()[0]
    assert stale["status"] == "stale" and stale["value"] is None and not stale["alerting"]
    await storage_ha_sensor_manager.apply(db_session, [sensor], {sensor.entity_id: None})
    unavailable = (await async_client.get(f"{BASE}/readings")).json()[0]
    assert unavailable["status"] == "unavailable" and unavailable["value"] is None
    storage_ha_sensor_manager.forget(sensor.id)
    assert (await async_client.get(f"{BASE}/readings")).json()[0]["status"] == "stale"


@pytest.mark.asyncio
async def test_threshold_edges_outage_recovery_restart_and_notification_failure(async_client, db_session):
    row = await location(db_session)
    created = await bind(async_client, row, alert_above=50, notify_on_alert=True)
    sensor = await db_session.get(StorageHASensor, created.json()["id"])
    manager = StorageHASensorManager()
    with patch("backend.app.services.storage_ha_sensors.send_storage_alert", AsyncMock()) as notify:
        for value in [60, 60, None, 60, 50, 51, None, 51, 40, 60]:
            payload = None if value is None else {"state": str(value)}
            await manager.apply(db_session, [sensor], {sensor.entity_id: payload})
        assert notify.await_count == 2
        # A restart on an existing alert creates no false transition.
        await StorageHASensorManager().apply(db_session, [sensor], {sensor.entity_id: {"state": "60"}})
        assert notify.await_count == 2
        notify.side_effect = RuntimeError("provider offline")
        await manager.apply(db_session, [sensor], {sensor.entity_id: {"state": "40"}})
        await manager.apply(db_session, [sensor], {sensor.entity_id: {"state": "60"}})
        assert manager.get_reading(sensor.id).value == 60
        await manager.apply(db_session, [sensor], {sensor.entity_id: {"state": "60"}})
        assert notify.await_count == 3


@pytest.mark.asyncio
async def test_poll_reuses_fetch_and_cannot_interlock_storage(async_client, db_session, printer_factory):
    row = await location(db_session)
    created = await bind(async_client, row, alert_above=50, notify_on_alert=True)
    printer = await printer_factory()
    db_session.add(
        PrinterHASensor(printer_id=printer.id, name="Peer humidity", entity_id=HUMIDITY["entity_id"], kind="numeric")
    )
    await db_session.commit()
    manager = HASensorManager()

    @asynccontextmanager
    async def session():
        yield db_session

    with (
        patch("backend.app.core.database.async_session", session),
        patch.object(manager, "_configure", AsyncMock(return_value=True)),
        patch(
            "backend.app.services.ha_sensor_manager.homeassistant_service.fetch_states",
            AsyncMock(return_value={HUMIDITY["entity_id"]: {"state": "60"}}),
        ) as fetch,
    ):
        await manager.poll_once()
        fetch.assert_awaited_once_with([HUMIDITY["entity_id"]])
    assert storage_ha_sensor_manager.get_reading(created.json()["id"]).alerting is True
    assert await manager.blocked_printers(db_session) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "unknown", "unavailable", "NaN", "inf", "calibrating-" + "x" * 500])
async def test_invalid_readings_do_not_poison_storage_persistence(async_client, db_session, value):
    row = await location(db_session)
    response = await bind(async_client, row)
    sensor = await db_session.get(StorageHASensor, response.json()["id"])
    manager = StorageHASensorManager()
    await manager.apply(db_session, [sensor], {sensor.entity_id: {"state": "0" * 100 + "42"}})
    assert len(sensor.last_state) == 64
    assert manager.get_reading(sensor.id).value == 42
    await manager.apply(db_session, [sensor], {sensor.entity_id: {"state": value}})
    assert not manager.get_reading(sensor.id).reachable
    assert sensor.last_state == "0" * 64
    assert sensor.last_read_at is not None


@pytest.mark.asyncio
async def test_changed_unit_unavailable_and_location_delete_cascades(async_client, db_session):
    row = await location(db_session)
    response = await bind(async_client, row)
    sensor = await db_session.get(StorageHASensor, response.json()["id"])
    await storage_ha_sensor_manager.apply(
        db_session, [sensor], {sensor.entity_id: {"state": "42", "attributes": {"unit_of_measurement": "°C"}}}
    )
    assert not storage_ha_sensor_manager.get_reading(sensor.id).reachable
    assert (await async_client.delete(f"/api/v1/inventory/locations/{row.id}")).status_code == 200
    assert (await async_client.get(f"{BASE}/")).json() == []


@pytest.mark.asyncio
async def test_no_ha_configuration_leaves_catalog_usable(async_client, db_session):
    row = await location(db_session)
    assert (await bind(async_client, row)).status_code == 201
    assert (await async_client.get(f"{BASE}/entities")).status_code == 400
    assert (await async_client.get("/api/v1/inventory/locations")).status_code == 200
    with (
        patch(
            "backend.app.api.routes.settings.get_homeassistant_settings",
            AsyncMock(return_value={"ha_enabled": False, "ha_url": "http://homeassistant.local", "ha_token": "test"}),
        ),
        patch("backend.app.services.ha_sensor_manager.homeassistant_service.fetch_states", AsyncMock()) as fetch,
    ):
        assert await HASensorManager()._configure(db_session) is False
        fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_every_route_requires_auth_and_storage_permissions(async_client, db_session):
    row = await location(db_session)
    created = await bind(async_client, row)
    sensor_id = created.json()["id"]
    routes = [
        ("GET", f"{BASE}/", None),
        ("GET", f"{BASE}/readings", None),
        ("GET", f"{BASE}/entities", None),
        ("POST", f"{BASE}/", {**HUMIDITY, "location_id": row.id}),
        ("PATCH", f"{BASE}/{sensor_id}", {"name": "Changed"}),
        ("DELETE", f"{BASE}/{sensor_id}", None),
    ]
    group = Group(
        name="HA operator",
        permissions=["smart_plugs:read", "smart_plugs:create", "smart_plugs:update", "smart_plugs:delete"],
    )
    user = User(username="ha_operator", password_hash="unused", role="user")
    user.groups.append(group)
    db_session.add_all([group, user])
    await db_session.commit()
    token = create_access_token(data={"sub": user.username})
    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        for method, url, data in routes:
            assert (await async_client.request(method, url, json=data)).status_code == 401
            assert (
                await async_client.request(method, url, json=data, headers={"Authorization": f"Bearer {token}"})
            ).status_code == 403
        group.permissions = ["inventory:read"]
        await db_session.commit()
        assert (await async_client.get(f"{BASE}/", headers={"Authorization": f"Bearer {token}"})).status_code == 200
        assert (
            await async_client.patch(
                f"{BASE}/{sensor_id}", json={"name": "Changed"}, headers={"Authorization": f"Bearer {token}"}
            )
        ).status_code == 403
        group.permissions = ["inventory:read", "inventory:update"]
        await db_session.commit()
        assert (
            await async_client.patch(
                f"{BASE}/{sensor_id}", json={"name": "Changed"}, headers={"Authorization": f"Bearer {token}"}
            )
        ).status_code == 200


@pytest.mark.asyncio
async def test_environment_alert_cannot_change_stock_or_reservations(async_client, db_session):
    from backend.tests.integration.test_order_reservation_lifecycle import _accepted_order

    order, _, spool = await _accepted_order(async_client, db_session)
    row = await location(db_session)
    spool.location_id, spool.storage_location = row.id, row.name
    await db_session.commit()
    before = (await async_client.get(f"/api/v1/orders/{order['id']}")).json()
    stock_before = (spool.label_weight, spool.weight_used, spool.location_id)
    created = await bind(async_client, row, alert_above=50, notify_on_alert=True)
    sensor = await db_session.get(StorageHASensor, created.json()["id"])
    with patch("backend.app.services.storage_ha_sensors.send_storage_alert", AsyncMock()):
        for payload in [{"state": "40"}, {"state": "60"}, None, {"state": "60"}]:
            await storage_ha_sensor_manager.apply(db_session, [sensor], {sensor.entity_id: payload})
    await db_session.refresh(spool)
    assert (spool.label_weight, spool.weight_used, spool.location_id) == stock_before
    after = (await async_client.get(f"/api/v1/orders/{order['id']}")).json()
    assert after == before


@pytest.mark.asyncio
async def test_existing_database_provider_opt_in_upgrade_is_idempotent(test_engine):
    from sqlalchemy import inspect, text

    from backend.app.core.database import _migrate_document_payments

    async with test_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE notification_providers DROP COLUMN on_storage_sensor_alert"))
        await _migrate_document_payments(conn)
        await _migrate_document_payments(conn)
        columns = await conn.run_sync(lambda sync: inspect(sync).get_columns("notification_providers"))
        option = next(column for column in columns if column["name"] == "on_storage_sensor_alert")
        assert option["default"] == "FALSE"


@pytest.mark.asyncio
async def test_entity_picker_only_offers_environmental_sensors(async_client):
    rows = [
        {
            "entity_id": "sensor.humidity",
            "domain": "sensor",
            "friendly_name": "Humidity",
            "device_class": "humidity",
            "unit_of_measurement": "%",
        },
        {
            "entity_id": "sensor.temperature",
            "domain": "sensor",
            "friendly_name": "Temperature",
            "device_class": "temperature",
            "unit_of_measurement": "°F",
        },
        {
            "entity_id": "sensor.power",
            "domain": "sensor",
            "friendly_name": "Power",
            "device_class": "power",
            "unit_of_measurement": "W",
        },
        {"entity_id": "binary_sensor.door", "domain": "binary_sensor", "friendly_name": "Door", "device_class": "door"},
    ]
    settings = {"ha_enabled": True, "ha_url": "http://homeassistant.local:8123", "ha_token": "test"}
    with (
        patch("backend.app.api.routes.settings.get_homeassistant_settings", AsyncMock(return_value=settings)),
        patch(
            "backend.app.services.homeassistant.homeassistant_service.list_display_entities",
            AsyncMock(return_value=rows),
        ),
    ):
        result = await async_client.get(f"{BASE}/entities")
    assert result.status_code == 200
    assert [row["entity_id"] for row in result.json()] == ["sensor.humidity", "sensor.temperature"]


@pytest.mark.asyncio
async def test_lower_threshold_transition_and_independent_peer_reading(async_client, db_session):
    row = await location(db_session)
    humidity = (await bind(async_client, row, alert_below=30, notify_on_alert=True)).json()
    temperature = (
        await bind(
            async_client, row, entity_id="sensor.temperature", name="Temperature", device_class="temperature", unit="°C"
        )
    ).json()
    sensors = [await db_session.get(StorageHASensor, item["id"]) for item in [humidity, temperature]]
    manager = StorageHASensorManager()
    with patch("backend.app.services.storage_ha_sensors.send_storage_alert", AsyncMock()) as notify:
        await manager.apply(db_session, sensors, {sensors[0].entity_id: {"state": "30"}, sensors[1].entity_id: []})
        await manager.apply(
            db_session, sensors, {sensors[0].entity_id: {"state": "29"}, sensors[1].entity_id: {"state": "20.5"}}
        )
        assert notify.await_count == 1
    assert manager.get_reading(sensors[1].id).value == 20.5
    # A duplicate entity can be bound to another existing location safely.
    other = Location()
    assign_location_name(other, "Second shelf")
    db_session.add(other)
    await db_session.commit()
    assert (await bind(async_client, other)).status_code == 201
