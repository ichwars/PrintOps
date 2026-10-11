"""Exercise inventory and Spoolman decisions through the real AMS callback."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.spoolman import SpoolmanClient


@pytest.fixture
async def slot_context(async_client, printer_factory, db_session, monkeypatch):
    from backend.app import main

    printer = await printer_factory(model="X1C")
    spool = Spool(material="PLA", rgba="FF0000FF", label_weight=1000)
    db_session.add(spool)
    await db_session.flush()
    row = SpoolAssignment(
        printer_id=printer.id,
        spool_id=spool.id,
        ams_id=0,
        tray_id=0,
        fingerprint_color="FF0000FF",
        fingerprint_type="PLA",
    )
    db_session.add(row)
    await db_session.commit()
    client = BambuMQTTClient("10.0.0.7", "PRESENCE", "12345678", model="X1C")
    client.state.state = "IDLE"
    client.state.connected = True
    monkeypatch.setattr(main.printer_manager, "get_status", lambda _: client.state)
    monkeypatch.setattr(main.printer_manager, "get_model", lambda _: "X1C")
    monkeypatch.setattr(main.ws_manager, "send_printer_status", AsyncMock())
    monkeypatch.setattr(main.ws_manager, "broadcast", AsyncMock())

    async def report(tray):
        data = [{"id": 0, "tray": [tray]}]
        client.state.raw_data = {"ams": data}
        await main.on_ams_change(printer.id, data)
        db_session.expunge_all()

    return printer.id, spool.id, row.id, client, report


@pytest.mark.asyncio
@pytest.mark.parametrize("ams_id", [0, 128])
async def test_presence_bit_overrules_stale_empty_state_on_assign(async_client, slot_context, monkeypatch, ams_id):
    printer_id, spool_id, _, client, _ = slot_context
    client.state.raw_data = {
        "ams": [{"id": ams_id, "tray": [{"id": 0, "state": 9, "exists": True, "tray_type": "", "tray_color": ""}]}]
    }
    mqtt = MagicMock()
    mqtt.ams_set_filament_setting.return_value = True
    monkeypatch.setattr("backend.app.services.printer_manager.printer_manager.get_client", lambda _: mqtt)
    response = await async_client.post(
        "/api/v1/inventory/assignments",
        json={
            "printer_id": printer_id,
            "spool_id": spool_id,
            "ams_id": ams_id,
            "tray_id": 0,
        },
    )
    assert response.status_code == 200
    assert response.json()["pending_config"] is False


@pytest.mark.asyncio
async def test_occupied_blank_tray_keeps_inventory_identity(slot_context, db_session):
    _, _, row_id, _, report = slot_context
    await report({"id": 0, "state": 9, "exists": True, "tray_type": "", "tray_color": ""})
    assert await db_session.get(SpoolAssignment, row_id) is not None


@pytest.mark.asyncio
async def test_one_empty_push_keeps_inventory_identity(slot_context, db_session):
    _, _, row_id, _, report = slot_context
    await report({"id": 0, "exists": False, "tray_type": "", "tray_color": ""})
    assert await db_session.get(SpoolAssignment, row_id) is not None


@pytest.mark.asyncio
async def test_presence_bit_replays_pending_configuration(slot_context, db_session, monkeypatch):
    _, _, row_id, _, report = slot_context
    row = await db_session.get(SpoolAssignment, row_id)
    row.fingerprint_type = ""
    row.fingerprint_color = ""
    await db_session.commit()
    mqtt = MagicMock()
    mqtt.ams_set_filament_setting.return_value = True
    monkeypatch.setattr("backend.app.services.printer_manager.printer_manager.get_client", lambda _: mqtt)
    await report({"id": 0, "state": 9, "exists": True, "tray_type": "", "tray_color": ""})
    row = await db_session.get(SpoolAssignment, row_id)
    assert row is not None
    assert row.fingerprint_type == "PLA"


@pytest.mark.asyncio
@pytest.mark.parametrize("exists", [True, False])
async def test_blank_spoolman_push_keeps_slot_identity(slot_context, db_session, monkeypatch, exists):
    from backend.app import main

    printer_id, _, _, _, report = slot_context
    db_session.add_all(
        [
            Settings(key="spoolman_enabled", value="true"),
            Settings(key="spoolman_sync_mode", value="auto"),
            Settings(key="spoolman_url", value="http://spoolman.test"),
        ]
    )
    row = SpoolmanSlotAssignment(printer_id=printer_id, ams_id=0, tray_id=0, spoolman_spool_id=42)
    db_session.add(row)
    await db_session.commit()
    row_id = row.id
    client = SpoolmanClient("http://spoolman.test")
    monkeypatch.setattr(client, "health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(client, "get_spools", AsyncMock(return_value=[]))
    monkeypatch.setattr(main, "get_spoolman_client", AsyncMock(return_value=client))
    await report({"id": 0, "exists": exists, "tray_type": "", "tray_color": ""})
    assert await db_session.get(SpoolmanSlotAssignment, row_id) is not None


@pytest.mark.asyncio
async def test_confirmed_empty_is_removed_by_recheck_without_new_push(slot_context, db_session, monkeypatch):
    from backend.app import main
    from backend.app.services import slot_unlink_grace

    now = [1000.0]
    monkeypatch.setattr(slot_unlink_grace, "_now", lambda: now[0])
    printer_id, _, row_id, _, report = slot_context
    await report({"id": 0, "exists": False, "tray_type": "", "tray_color": ""})
    assert await db_session.get(SpoolAssignment, row_id) is not None
    now[0] += 120
    await main._recheck_held_unlinks(printer_id)
    db_session.expunge_all()
    assert await db_session.get(SpoolAssignment, row_id) is None


@pytest.mark.asyncio
async def test_recovery_cancels_old_removal_deadline(slot_context, db_session, monkeypatch):
    from backend.app.services import slot_unlink_grace

    now = [1000.0]
    monkeypatch.setattr(slot_unlink_grace, "_now", lambda: now[0])
    _, _, row_id, _, report = slot_context
    await report({"id": 0, "exists": False, "tray_type": "", "tray_color": ""})
    now[0] += 60
    await report({"id": 0, "exists": True, "tray_type": "PLA", "tray_color": "FF0000FF"})
    now[0] += 60
    await report({"id": 0, "exists": False, "tray_type": "", "tray_color": ""})
    assert await db_session.get(SpoolAssignment, row_id) is not None


@pytest.mark.asyncio
async def test_disconnected_cache_cannot_confirm_removal(slot_context, db_session, monkeypatch):
    from backend.app import main
    from backend.app.services import slot_unlink_grace

    now = [1000.0]
    monkeypatch.setattr(slot_unlink_grace, "_now", lambda: now[0])
    printer_id, _, row_id, client, report = slot_context
    await report({"id": 0, "exists": False, "tray_type": "", "tray_color": ""})
    client.state.connected = False
    now[0] += 120
    await main._recheck_held_unlinks(printer_id)
    db_session.expunge_all()
    assert await db_session.get(SpoolAssignment, row_id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("sync_all", [False, True])
async def test_manual_spoolman_sync_holds_empty_slot(async_client, slot_context, db_session, monkeypatch, sync_all):
    printer_id, _, _, client, _ = slot_context
    db_session.add_all(
        [Settings(key="spoolman_enabled", value="true"), Settings(key="spoolman_url", value="http://spoolman.test")]
    )
    row = SpoolmanSlotAssignment(printer_id=printer_id, ams_id=0, tray_id=0, spoolman_spool_id=42)
    db_session.add(row)
    await db_session.commit()
    row_id = row.id
    sm = SpoolmanClient("http://spoolman.test")
    monkeypatch.setattr(sm, "health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(sm, "get_spools", AsyncMock(return_value=[]))
    monkeypatch.setattr("backend.app.api.routes.spoolman.get_spoolman_client", AsyncMock(return_value=sm))
    client.state.raw_data = {
        "ams": [{"id": 0, "tray": [{"id": 0, "exists": False, "tray_type": "", "tray_color": ""}]}]
    }
    path = "/api/v1/spoolman/sync-all" if sync_all else f"/api/v1/spoolman/sync/{printer_id}"
    response = await async_client.post(path)
    assert response.status_code == 200, response.text
    db_session.expunge_all()
    assert await db_session.get(SpoolmanSlotAssignment, row_id) is not None


@pytest.mark.asyncio
async def test_reassigning_same_spoolman_spool_discards_old_removal(
    async_client, slot_context, db_session, monkeypatch
):
    from backend.app.services import slot_unlink_grace

    printer_id, _, _, _, _ = slot_context
    db_session.add(SpoolmanSlotAssignment(printer_id=printer_id, ams_id=0, tray_id=0, spoolman_spool_id=42))
    await db_session.commit()
    now = [1000.0]
    monkeypatch.setattr(slot_unlink_grace, "_now", lambda: now[0])
    slot_unlink_grace.removal_confirmed(printer_id, ("spoolman", 0, 0, 42))
    sm = SpoolmanClient("http://spoolman.test")
    monkeypatch.setattr(sm, "get_spool", AsyncMock(return_value={"id": 42, "filament": {"weight": 1000}}))
    monkeypatch.setattr(sm, "get_all_spools", AsyncMock(return_value=[]))
    monkeypatch.setattr(sm, "get_spools", AsyncMock(return_value=[]))

    async def get_client(_):
        return sm

    monkeypatch.setattr("backend.app.api.routes.spoolman_inventory._get_client", get_client)
    response = await async_client.post(
        "/api/v1/spoolman/inventory/slot-assignments",
        json={
            "printer_id": printer_id,
            "ams_id": 0,
            "tray_id": 0,
            "spoolman_spool_id": 42,
        },
    )
    assert response.status_code == 200, response.text
    now[0] += 120
    assert slot_unlink_grace.removal_confirmed(printer_id, ("spoolman", 0, 0, 42)) is False
