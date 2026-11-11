"""REST status and pushed status retain the same AMS and machine evidence."""

from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.bambu_mqtt import NozzleInfo, PrinterState
from backend.app.services.printer_manager import printer_state_to_dict

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_rest_and_websocket_share_empty_slot_and_drying_fields(async_client, printer_factory):
    printer = await printer_factory(model="H2D Pro")
    state = PrinterState()
    state.connected = True
    state.ams_extruder_map = {"0": 1}
    state.print_ams_mapping = [0]
    state.raw_data = {
        "ams": [
            {
                "id": 0,
                "tray": [{"id": 0}],
                "dry_status": 3,
                "dry_sub_status": 2,
                "dry_sf_reason": [8],
                "sw_ver": "01.02",
                "sn": "AMS1",
            }
        ],
        "vt_tray": {"id": 254, "tray_type": "PLA"},
    }
    state.nozzles = [NozzleInfo(nozzle_type="HS00", nozzle_diameter="0.4")]
    state.h2d_extruder_snow = {0: 2, 1: 255}
    state.firmware_version = "01.02"
    state.developer_mode = True
    state.airduct_mode = 1
    state.nozzle_rack = [{"id": 0, "filament_type": "PLA"}]
    with patch("backend.app.api.routes.printers_status.printer_manager") as manager:
        manager.get_status.return_value = state
        manager.get_drying_targets.return_value = {}
        manager.is_awaiting_plate_clear.return_value = False
        response = await async_client.get(f"/api/v1/printers/{printer.id}/status")
    assert response.status_code == 200, response.text
    rest = response.json()
    push = printer_state_to_dict(state, model=printer.model)
    for key in (
        "ams",
        "vt_tray",
        "extruder_slots",
        "ams_extruder_map",
        "print_ams_mapping",
        "nozzles",
        "firmware_version",
        "developer_mode",
        "airduct_mode",
        "nozzle_rack",
    ):
        assert rest[key] == push[key], key
    assert rest["ams"][0]["tray"][0]["state"] == 9
    assert rest["ams"][0]["dry_sf_reason"] == [8]


@pytest.mark.parametrize("mapping", [None, [9]])
async def test_restart_mapping_restores_only_when_no_new_capture_exists(db_session, printer_factory, mapping):
    from datetime import datetime, timezone

    from backend.app.models.active_print_session import ActivePrintSession
    from backend.app.services.active_print_provenance import restore_for_running_print
    from backend.app.services.usage_tracker import _active_sessions

    printer = await printer_factory()
    db_session.add(
        ActivePrintSession(
            printer_id=printer.id,
            print_name="part",
            subtask_id="8",
            started_at=datetime.now(timezone.utc),
            ams_mapping=[1, 2],
            spool_assignments={},
            tray_change_log=[],
        )
    )
    await db_session.commit()
    state = PrinterState()
    state.subtask_name = "part"
    state.subtask_id = "8"
    state.print_ams_mapping = mapping
    try:
        await restore_for_running_print(printer.id, state, db_session, MagicMock())
        assert state.print_ams_mapping == ([1, 2] if mapping is None else mapping)
    finally:
        _active_sessions.pop(printer.id, None)


async def test_runout_narrows_by_nozzle_but_not_stale_fts_wiring(async_client, printer_factory):
    from backend.app.services.bambu_mqtt import FilaSwitchState

    printer = await printer_factory(model="H2D")
    state = PrinterState(state="PAUSE", connected=True, active_extruder=1, tray_tar=2, tray_pre=2)
    state.ams_extruder_map = {"0": 0, "1": 1}
    state.raw_data = {"ams": [{"id": 0, "tray": [{"id": 2}]}, {"id": 1, "tray": [{"id": 2}]}], "mapping": [2, 258]}
    with patch("backend.app.api.routes.printers_status.printer_manager") as pm:
        pm.get_status.return_value = state
        pm.get_drying_targets.return_value = {}
        pm.is_awaiting_plate_clear.return_value = False
        for switched in (False, True):
            state.fila_switch = FilaSwitchState(installed=switched)
            rest = (await async_client.get(f"/api/v1/printers/{printer.id}/status")).json()
            push = printer_state_to_dict(state, model=printer.model)
            assert rest["expected_tray"] == push["expected_tray"] == (None if switched else 6)


async def test_extruder_feed_occupancy_preserves_inactive_nozzle_and_excludes_unknown_values():
    from backend.app.services.printer_status_slots import extruder_slots

    state = PrinterState()
    state.h2d_extruder_snow = {0: 6, 1: 128, 2: 10}
    assert extruder_slots(state) == {
        "0": {"ams_id": 1, "has_filament": True},
        "1": {"ams_id": 128, "has_filament": True},
    }
    state.h2d_extruder_snow = {0: 255, 1: 254}
    assert extruder_slots(state) == {
        "0": {"ams_id": None, "has_filament": False},
        "1": {"ams_id": None, "has_filament": True},
    }
