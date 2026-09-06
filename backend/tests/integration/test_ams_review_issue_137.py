"""Regression coverage for the PR review findings on issue #137."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment


def _mqtt():
    client = MagicMock()
    client.ams_set_filament_setting.return_value = True
    client.extrusion_cali_sel.return_value = True
    return client


def _status(tray_type: str, tray_info_idx: str):
    status = MagicMock()
    status.raw_data = {
        "ams": {
            "ams": [
                {
                    "id": 0,
                    "tray": [
                        {
                            "id": 1,
                            "tray_type": tray_type,
                            "tray_info_idx": tray_info_idx,
                            "tray_color": "09FF00FF",
                            "state": 11,
                        }
                    ],
                }
            ]
        }
    }
    status.nozzles = [MagicMock(nozzle_diameter="0.4")]
    status.ams_extruder_map = None
    status.kprofiles = []
    status.state = "IDLE"
    return status


@pytest.mark.asyncio
@pytest.mark.integration
async def test_manual_slot_reuses_specific_preset_from_legacy_product_type(async_client, printer_factory):
    printer = await printer_factory(model="P1S")
    mqtt = _mqtt()
    with patch("backend.app.api.routes.printers_ams.printer_manager") as manager:
        manager.get_client.return_value = mqtt
        manager.get_status.return_value = _status("PLA+", "P4d64437")
        response = await async_client.post(
            f"/api/v1/printers/{printer.id}/slots/0/1/configure",
            params={
                "tray_info_idx": "",
                "tray_type": "PLA+",
                "tray_sub_brands": "eSUN PLA+",
                "tray_color": "09ff00ff",
                "nozzle_temp_min": 190,
                "nozzle_temp_max": 230,
            },
        )

    assert response.status_code == 200
    assert mqtt.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == "P4d64437"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_internal_assignment_reuses_specific_preset_from_legacy_product_type(
    async_client, db_session, printer_factory
):
    printer = await printer_factory(model="P1S")
    spool = Spool(material="PLA+", brand="eSUN", rgba="09ff00ff", label_weight=1000, weight_used=0)
    db_session.add(spool)
    await db_session.commit()
    mqtt = _mqtt()
    with patch("backend.app.services.printer_manager.printer_manager") as manager:
        manager.get_client.return_value = mqtt
        manager.get_status.return_value = _status("PLA+", "P4d64437")
        response = await async_client.post(
            "/api/v1/inventory/assignments",
            json={"spool_id": spool.id, "printer_id": printer.id, "ams_id": 0, "tray_id": 1},
        )

    assert response.status_code == 200
    assert mqtt.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == "P4d64437"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_internal_assignment_persists_cloud_protocol_type_for_telemetry(
    async_client, db_session, printer_factory
):
    printer = await printer_factory(model="P1S")
    spool = Spool(
        material="CPE HG100",
        brand="Fillamentum",
        rgba="09ff00ff",
        slicer_filament="GFS137",
        slicer_filament_name="CPE HG100",
        label_weight=1000,
        weight_used=0,
    )
    db_session.add(spool)
    await db_session.commit()
    mqtt = _mqtt()
    with (
        patch("backend.app.services.printer_manager.printer_manager") as manager,
        patch(
            "backend.app.api.routes.inventory.resolve_slicer_filament",
            AsyncMock(return_value=("GFG99", "GFS137", "Fillamentum CPE", "PETG")),
        ),
    ):
        manager.get_client.return_value = mqtt
        manager.get_status.return_value = _status("CPE", "P4d64437")
        response = await async_client.post(
            "/api/v1/inventory/assignments",
            json={"spool_id": spool.id, "printer_id": printer.id, "ams_id": 0, "tray_id": 1},
        )

    assert response.status_code == 200
    assignment = await db_session.scalar(select(SpoolAssignment).where(SpoolAssignment.spool_id == spool.id))
    assert mqtt.ams_set_filament_setting.call_args.kwargs["tray_type"] == "PETG"
    assert assignment.fingerprint_type == "PETG"
