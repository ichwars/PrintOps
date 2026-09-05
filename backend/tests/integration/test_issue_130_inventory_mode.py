"""Inventory mode changes preserve inactive assignments (issue #130)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment


def _status(ams_data):
    status = MagicMock()
    status.raw_data = {"ams": ams_data, "vt_tray": []}
    status.state = "IDLE"
    return status


async def _run_ams_change(printer_id: int, ams_data: list, *, spoolman_mode: bool):
    from backend.app.main import on_ams_change

    status = _status(ams_data)
    with (
        patch("backend.app.main.printer_manager") as manager,
        patch("backend.app.main.mqtt_relay") as relay,
        patch("backend.app.main.ws_manager") as websocket,
        patch("backend.app.main.get_spoolman_client", new_callable=AsyncMock, return_value=None),
        patch(
            "backend.app.services.inventory_mode.spoolman_owns_assignments",
            new_callable=AsyncMock,
            return_value=spoolman_mode,
        ),
    ):
        manager.get_printer.return_value = MagicMock(name="P", serial_number="SER")
        manager.get_status.return_value = status
        manager.get_client.return_value = MagicMock()
        manager.get_model.return_value = "X1C"
        relay.on_ams_change = AsyncMock()
        websocket.send_printer_status = AsyncMock()
        websocket.broadcast = AsyncMock()
        await on_ams_change(printer_id, ams_data)


async def _assignment(db_session, printer, *, spoolman_enabled: bool):
    spool = Spool(material="PLA", rgba="FF0000FF")
    db_session.add_all(
        [
            spool,
            Settings(key="spoolman_enabled", value=str(spoolman_enabled).lower()),
        ]
    )
    await db_session.flush()
    db_session.add(
        SpoolAssignment(
            spool_id=spool.id,
            printer_id=printer.id,
            ams_id=0,
            tray_id=0,
            fingerprint_color="FF0000FF",
            fingerprint_type="PLA",
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_spoolman_mode_does_not_unlink_preserved_built_in_assignment(
    async_client,
    db_session,
    printer_factory,
):
    printer = await printer_factory(name="P1S")
    await _assignment(db_session, printer, spoolman_enabled=True)

    await _run_ams_change(
        printer.id,
        [{"id": 0, "tray": [{"id": 0, "tray_type": "PETG", "tray_color": "00FF00FF", "state": 11}]}],
        spoolman_mode=True,
    )

    rows = await db_session.execute(select(SpoolAssignment).where(SpoolAssignment.printer_id == printer.id))
    assert len(rows.scalars().all()) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_built_in_mode_still_unlinks_stale_active_assignment(async_client, db_session, printer_factory):
    printer = await printer_factory(name="P1S")
    await _assignment(db_session, printer, spoolman_enabled=False)

    await _run_ams_change(
        printer.id,
        [{"id": 0, "tray": [{"id": 0, "tray_type": "PETG", "tray_color": "00FF00FF", "state": 11}]}],
        spoolman_mode=False,
    )

    rows = await db_session.execute(select(SpoolAssignment).where(SpoolAssignment.printer_id == printer.id))
    assert rows.scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unreachable_spoolman_mode_does_not_fall_back_to_local_tag_lookup(async_client, db_session):
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    await db_session.commit()

    with (
        patch("backend.app.api.routes.spoolbuddy.get_spool_by_tag", new_callable=AsyncMock) as local_lookup,
        patch("backend.app.api.routes.spoolbuddy.ws_manager.broadcast", new_callable=AsyncMock) as broadcast,
    ):
        response = await async_client.post(
            "/api/v1/spoolbuddy/nfc/tag-scanned",
            json={"device_id": "sb-1", "tag_uid": "AABB1122"},
        )

    assert response.status_code == 200
    assert response.json()["matched"] is False
    local_lookup.assert_not_awaited()
    assert broadcast.await_args.args[0]["type"] == "spoolman_unavailable"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unreachable_spoolman_mode_does_not_update_same_id_local_spool(async_client, db_session):
    spool = Spool(material="PLA", rgba="FF0000FF", label_weight=1000, core_weight=250, weight_used=100)
    db_session.add_all([spool, Settings(key="spoolman_enabled", value="true")])
    await db_session.commit()
    await db_session.refresh(spool)

    response = await async_client.post(
        "/api/v1/spoolbuddy/scale/update-spool-weight",
        json={"spool_id": spool.id, "weight_grams": 500},
    )

    assert response.status_code == 503
    await db_session.refresh(spool)
    assert spool.weight_used == 100
