"""Integration tests for the printer-bound Home Assistant sensor API (#1148)."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.core.auth import create_access_token
from backend.app.core.permissions import Permission
from backend.app.models.group import Group
from backend.app.models.printer_ha_sensor import PrinterHAInterlockAudit
from backend.app.models.user import User
from backend.app.services.ha_sensor_manager import SensorReading, ha_sensor_manager

DOOR = {
    "name": "Enclosure Door",
    "entity_id": "binary_sensor.enclosure_door",
    "kind": "binary",
    "device_class": "door",
    "alert_state": "on",
}
TEMP = {
    "name": "Enclosure Temp",
    "entity_id": "sensor.enclosure_temp",
    "kind": "numeric",
    "device_class": "temperature",
    "unit": "°C",
}


@pytest.fixture(autouse=True)
def _no_live_ha():
    """Creating or editing a sensor reads it once; keep that off the network."""
    with patch.object(ha_sensor_manager, "refresh_one", AsyncMock()):
        yield


@pytest.fixture(autouse=True)
def _clean_cache():
    yield
    ha_sensor_manager._readings.clear()
    ha_sensor_manager._last_alerting.clear()
    ha_sensor_manager._overrides.clear()


async def _permission_token(db_session, *, username: str, permissions: list[str]) -> str:
    group = Group(name=f"{username}-permissions", permissions=permissions)
    user = User(username=username, password_hash="unused", role="user")
    user.groups.append(group)
    db_session.add_all([group, user])
    await db_session.commit()
    return create_access_token(data={"sub": username})


class TestCrud:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bind_a_door_contact(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory()

        response = await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": printer.id})

        assert response.status_code == 200
        body = response.json()
        assert body["entity_id"] == "binary_sensor.enclosure_door"
        assert body["kind"] == "binary"
        assert body["show_on_printer_card"] is True
        # Display-only until the user opts in.
        assert body["block_print"] is False
        assert body["notify_on_alert"] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_a_switch(self, async_client: AsyncClient, printer_factory):
        """Switches are smart plugs; this table is read-only sensors."""
        printer = await printer_factory()

        response = await async_client.post(
            "/api/v1/ha-sensors/",
            json={**DOOR, "printer_id": printer.id, "entity_id": "switch.printer_plug"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_a_kind_that_contradicts_the_entity(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory()

        response = await async_client.post(
            "/api/v1/ha-sensors/",
            json={**TEMP, "printer_id": printer.id, "kind": "binary"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_an_interlock_with_nothing_to_trigger_on(self, async_client: AsyncClient, printer_factory):
        """block_print without an alert condition would never fire — that reads
        as a broken setting, not as a no-op."""
        printer = await printer_factory()

        response = await async_client.post(
            "/api/v1/ha-sensors/",
            json={**DOOR, "printer_id": printer.id, "alert_state": None, "block_print": True},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_a_duplicate_binding(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory()
        payload = {**DOOR, "printer_id": printer.id}
        await async_client.post("/api/v1/ha-sensors/", json=payload)

        response = await async_client.post("/api/v1/ha-sensors/", json=payload)

        assert response.status_code == 400
        assert "already bound" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_an_unknown_printer(self, async_client: AsyncClient):
        response = await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": 9999})

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_patch_revalidates_against_the_stored_row(self, async_client: AsyncClient, printer_factory):
        """The payload carries only block_print, so the coherence rule has to be
        re-run against the merged row, not against the patch alone."""
        printer = await printer_factory()
        created = await async_client.post(
            "/api/v1/ha-sensors/",
            json={**DOOR, "printer_id": printer.id, "alert_state": None},
        )
        sensor_id = created.json()["id"]

        response = await async_client.patch(f"/api/v1/ha-sensors/{sensor_id}", json={"block_print": True})

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_patch_accepts_a_coherent_change(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory()
        created = await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": printer.id})
        sensor_id = created.json()["id"]

        response = await async_client.patch(
            f"/api/v1/ha-sensors/{sensor_id}",
            json={"block_print": True, "notify_on_alert": True, "name": "Front Door"},
        )

        assert response.status_code == 200
        assert response.json()["block_print"] is True
        assert response.json()["name"] == "Front Door"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_drops_the_cached_reading(self, async_client: AsyncClient, printer_factory):
        """Otherwise a later sensor reusing the id inherits this one's state."""
        printer = await printer_factory()
        created = await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": printer.id})
        sensor_id = created.json()["id"]
        ha_sensor_manager._readings[sensor_id] = SensorReading("on", None, True, True)

        response = await async_client.delete(f"/api/v1/ha-sensors/{sensor_id}")

        assert response.status_code == 200
        assert ha_sensor_manager.get_reading(sensor_id) is None


class TestReadings:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_serves_the_cached_reading(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory()
        created = await async_client.post(
            "/api/v1/ha-sensors/",
            json={**TEMP, "printer_id": printer.id, "alert_above": 35},
        )
        sensor_id = created.json()["id"]
        ha_sensor_manager._readings[sensor_id] = SensorReading("41.2", 41.2, True, True)

        response = await async_client.get(f"/api/v1/ha-sensors/by-printer/{printer.id}/readings")

        assert response.status_code == 200
        reading = response.json()[0]
        assert reading["value"] == 41.2
        assert reading["alerting"] is True
        assert reading["unit"] == "°C"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_reading_names_the_saved_failure_strategy(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory()
        await async_client.post(
            "/api/v1/ha-sensors/",
            json={
                **DOOR,
                "printer_id": printer.id,
                "block_print": True,
                "failure_strategy": "fail_closed",
            },
        )

        response = await async_client.get(f"/api/v1/ha-sensors/by-printer/{printer.id}/readings")

        assert response.json()[0]["failure_strategy"] == "fail_closed"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unpolled_sensor_reports_unreachable_not_missing(self, async_client: AsyncClient, printer_factory):
        """Right after a restart the card should still list the sensor, greyed
        out — not drop it and reflow the layout."""
        printer = await printer_factory()
        await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": printer.id})

        response = await async_client.get(f"/api/v1/ha-sensors/by-printer/{printer.id}/readings")

        assert len(response.json()) == 1
        assert response.json()[0]["reachable"] is False
        assert response.json()[0]["alerting"] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hidden_sensors_stay_off_the_card(self, async_client: AsyncClient, printer_factory):
        """An interlock the user does not want cluttering the card still works."""
        printer = await printer_factory()
        await async_client.post(
            "/api/v1/ha-sensors/",
            json={**DOOR, "printer_id": printer.id, "show_on_printer_card": False},
        )

        response = await async_client.get(f"/api/v1/ha-sensors/by-printer/{printer.id}/readings")

        assert response.json() == []

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_readings_follow_sort_order(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory()
        await async_client.post(
            "/api/v1/ha-sensors/",
            json={**TEMP, "printer_id": printer.id, "sort_order": 2},
        )
        await async_client.post(
            "/api/v1/ha-sensors/",
            json={**DOOR, "printer_id": printer.id, "sort_order": 1},
        )

        response = await async_client.get(f"/api/v1/ha-sensors/by-printer/{printer.id}/readings")

        assert [r["name"] for r in response.json()] == ["Enclosure Door", "Enclosure Temp"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_other_printers_sensors_are_not_listed(self, async_client: AsyncClient, printer_factory):
        one = await printer_factory()
        two = await printer_factory(serial_number="OTHER123", name="Second")
        await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": one.id})

        response = await async_client.get(f"/api/v1/ha-sensors/by-printer/{two.id}/readings")

        assert response.json() == []


class TestEntityPicker:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_explains_itself_when_ha_is_not_configured(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.delenv("HA_URL", raising=False)
        monkeypatch.delenv("HA_TOKEN", raising=False)
        response = await async_client.get("/api/v1/ha-sensors/entities")

        assert response.status_code == 400
        assert "Home Assistant not configured" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_entities_is_not_parsed_as_a_sensor_id(self, async_client: AsyncClient):
        """Route ordering regression: /entities must not hit /{sensor_id}."""
        response = await async_client.get("/api/v1/ha-sensors/entities")

        assert response.status_code != 404


class TestCascadeAndUniqueness:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_patch_cannot_create_a_duplicate_binding(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory()
        await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": printer.id})
        second = await async_client.post("/api/v1/ha-sensors/", json={**TEMP, "printer_id": printer.id})

        response = await async_client.patch(
            f"/api/v1/ha-sensors/{second.json()['id']}",
            json={"entity_id": DOOR["entity_id"], "kind": "binary"},
        )

        assert response.status_code == 400
        assert "already bound" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_patch_to_the_same_entity_is_not_a_clash_with_itself(
        self, async_client: AsyncClient, printer_factory
    ):
        printer = await printer_factory()
        created = await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": printer.id})

        response = await async_client.patch(
            f"/api/v1/ha-sensors/{created.json()['id']}",
            json={"entity_id": DOOR["entity_id"], "name": "Front Door"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deleting_a_printer_takes_its_sensors(self, async_client: AsyncClient, printer_factory):
        """The relationship cascades, so no orphan row is left holding a
        printer_id that no longer resolves."""
        printer = await printer_factory()
        await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": printer.id})

        deleted = await async_client.delete(f"/api/v1/printers/{printer.id}")

        assert deleted.status_code == 200
        listed = await async_client.get("/api/v1/ha-sensors/")
        assert listed.json() == []


class TestSaveSurvivesHomeAssistant:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_succeeds_even_if_the_first_read_blows_up(self, async_client: AsyncClient, printer_factory):
        """The row is committed before the read. Reporting a failure for work
        that succeeded would send the user into a retry that 400s on the
        duplicate they just created."""
        printer = await printer_factory()

        with patch.object(ha_sensor_manager, "refresh_one", AsyncMock(side_effect=RuntimeError("HA said no"))):
            response = await async_client.post("/api/v1/ha-sensors/", json={**DOOR, "printer_id": printer.id})

        assert response.status_code == 200
        listed = await async_client.get(f"/api/v1/ha-sensors/?printer_id={printer.id}")
        assert len(listed.json()) == 1


class TestInterlockOverride:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_requires_queue_update_all_and_writes_durable_audit(
        self,
        async_client: AsyncClient,
        printer_factory,
        db_session,
    ):
        printer = await printer_factory(name="Safety Printer")
        await async_client.post(
            "/api/v1/ha-sensors/",
            json={
                **DOOR,
                "printer_id": printer.id,
                "block_print": True,
                "failure_strategy": "fail_closed",
            },
        )
        denied_token = await _permission_token(
            db_session,
            username="sensor-reader",
            permissions=[Permission.SMART_PLUGS_READ.value],
        )
        allowed_token = await _permission_token(
            db_session,
            username="queue-supervisor",
            permissions=[Permission.QUEUE_UPDATE_ALL.value],
        )
        endpoint = f"/api/v1/ha-sensors/printers/{printer.id}/interlock-override"

        with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
            denied = await async_client.post(
                endpoint,
                headers={"Authorization": f"Bearer {denied_token}"},
                json={"reason": "HA gateway maintenance"},
            )
            allowed = await async_client.post(
                endpoint,
                headers={"Authorization": f"Bearer {allowed_token}"},
                json={"reason": "HA gateway maintenance"},
            )

        assert denied.status_code == 403
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["overridden"] is True
        assert allowed.json()["username"] == "queue-supervisor"
        assert allowed.json()["created_at"]

        result = await db_session.execute(select(PrinterHAInterlockAudit))
        events = list(result.scalars().all())
        assert len(events) == 1
        assert events[0].action == "enabled"
        assert events[0].username == "queue-supervisor"
        assert events[0].printer_id == printer.id
        assert events[0].printer_name == "Safety Printer"
        assert events[0].reason == "HA gateway maintenance"
        assert events[0].created_at is not None

        with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
            cleared = await async_client.delete(
                endpoint,
                headers={"Authorization": f"Bearer {allowed_token}"},
            )
            audit = await async_client.get(
                f"/api/v1/ha-sensors/printers/{printer.id}/interlock-audit",
                headers={"Authorization": f"Bearer {allowed_token}"},
            )

        assert cleared.status_code == 200
        assert cleared.json()["overridden"] is False
        assert [event["action"] for event in audit.json()] == ["cleared", "enabled"]
        assert all(event["reason"] == "HA gateway maintenance" for event in audit.json())

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_positive_unsafe_state_cannot_be_overridden(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory()
        created = await async_client.post(
            "/api/v1/ha-sensors/",
            json={
                **DOOR,
                "printer_id": printer.id,
                "block_print": True,
                "failure_strategy": "fail_closed",
            },
        )
        ha_sensor_manager._readings[created.json()["id"]] = SensorReading("on", None, True, True)

        response = await async_client.post(
            f"/api/v1/ha-sensors/printers/{printer.id}/interlock-override",
            json={"reason": "Operator inspected the door"},
        )

        assert response.status_code == 409
        assert ha_sensor_manager.get_interlock_override(printer.id) is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deleting_a_sensor_revokes_its_printer_override(
        self, async_client: AsyncClient, printer_factory, db_session
    ):
        printer = await printer_factory(name="Delete Safety Printer")
        created = await async_client.post(
            "/api/v1/ha-sensors/",
            json={**DOOR, "printer_id": printer.id, "block_print": True, "failure_strategy": "fail_closed"},
        )
        endpoint = f"/api/v1/ha-sensors/printers/{printer.id}/interlock-override"
        enabled = await async_client.post(endpoint, json={"reason": "HA gateway maintenance"})
        assert enabled.status_code == 200

        deleted = await async_client.delete(f"/api/v1/ha-sensors/{created.json()['id']}")

        assert deleted.status_code == 200
        assert ha_sensor_manager.get_interlock_override(printer.id) is None
        events = list((await db_session.execute(select(PrinterHAInterlockAudit))).scalars().all())
        assert [event.action for event in events] == ["enabled", "cleared"]
        assert "sensor deleted" in events[-1].reason

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_updating_a_sensor_revokes_its_printer_override(
        self, async_client: AsyncClient, printer_factory, db_session
    ):
        printer = await printer_factory(name="Update Safety Printer")
        created = await async_client.post(
            "/api/v1/ha-sensors/",
            json={**DOOR, "printer_id": printer.id, "block_print": True, "failure_strategy": "fail_closed"},
        )
        endpoint = f"/api/v1/ha-sensors/printers/{printer.id}/interlock-override"
        enabled = await async_client.post(endpoint, json={"reason": "HA gateway maintenance"})
        assert enabled.status_code == 200

        updated = await async_client.patch(
            f"/api/v1/ha-sensors/{created.json()['id']}",
            json={"failure_strategy": "auto"},
        )

        assert updated.status_code == 200
        assert ha_sensor_manager.get_interlock_override(printer.id) is None
        events = list((await db_session.execute(select(PrinterHAInterlockAudit))).scalars().all())
        assert [event.action for event in events] == ["enabled", "cleared"]
        assert "sensor updated" in events[-1].reason
