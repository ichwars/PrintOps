"""Old position labels survive newly available AMS Lite serial metadata."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from backend.app.models.ams_label import AmsLabel
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.bambu_mqtt import BambuMQTTClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("physical,normalized", [(0, 0), (16, 6)])
async def test_lite_version_before_status_retains_serial_and_firmware(physical, normalized):
    client = BambuMQTTClient(ip_address="192.0.2.1", serial_number="TEST", access_code="test")
    client._handle_version_info({"module": [{"name": f"ams_f1/{physical}", "sn": "LITE123", "sw_ver": "01.02"}]})
    client._handle_ams_data({"ams": [{"id": physical, "tray": [{"id": 0}]}]})
    unit = client.state.raw_data["ams"][0]
    assert int(unit["id"]) == normalized
    assert (unit["sn"], unit["sw_ver"], unit["module_type"]) == ("LITE123", "01.02", "ams_f1")


@pytest.mark.parametrize("mode", ["internal", "spoolman"])
async def test_assignment_label_falls_back_when_the_serial_is_new(async_client, db_session, printer_factory, mode):
    printer = await printer_factory()
    db_session.add(AmsLabel(ams_serial_number=f"p{printer.id}a0", ams_id=0, label="Old Label"))
    if mode == "internal":
        spool = Spool(material="PLA")
        db_session.add(spool)
        await db_session.flush()
        db_session.add(SpoolAssignment(spool_id=spool.id, printer_id=printer.id, ams_id=0, tray_id=0))
        patch_path = "backend.app.services.printer_manager.printer_manager"
        path = "/api/v1/inventory/assignments"
    else:
        db_session.add(SpoolmanSlotAssignment(printer_id=printer.id, ams_id=0, tray_id=0, spoolman_spool_id=42))
        patch_path = "backend.app.api.routes.spoolman_inventory.printer_manager"
        path = "/api/v1/spoolman/inventory/slot-assignments/all"
    await db_session.commit()
    with patch(patch_path) as manager:
        manager.get_all_statuses.return_value = {printer.id: MagicMock(raw_data={"ams": [{"id": 0, "sn": "LITE123"}]})}
        response = await async_client.get(path)
    assert response.status_code == 200, response.text
    assert response.json()[0]["ams_label"] == "Old Label"


@pytest.mark.parametrize("action", ["save", "delete"])
async def test_serial_label_edit_removes_the_old_position_fallback(async_client, db_session, printer_factory, action):
    printer = await printer_factory()
    db_session.add(AmsLabel(ams_serial_number=f"p{printer.id}a0", ams_id=0, label="Old Label"))
    await db_session.commit()
    path = f"/api/v1/printers/{printer.id}/ams-labels/0"
    if action == "save":
        response = await async_client.put(path, json={"ams_serial": "LITE123", "label": "New Label"})
    else:
        response = await async_client.delete(path, params={"ams_serial": "LITE123"})
    assert response.status_code == 200, response.text
    labels = (await db_session.execute(select(AmsLabel))).scalars().all()
    assert [(label.ams_serial_number, label.label) for label in labels] == (
        [("LITE123", "New Label")] if action == "save" else []
    )
