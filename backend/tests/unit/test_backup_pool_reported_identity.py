"""Backup material identity follows the loaded tray, with PrintOps occupancy gates."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.models.settings import Settings
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.filament_deficit import (
    _live_tray_keys,
    _material_identity_internal,
    build_slot_materials,
    compute_deficit_for_queue_item,
)
from backend.tests.unit.services.test_filament_deficit import _assign, _queue_item, _setup_archive_3mf, _spool


def tray(slot, *, preset="GFA10", color="AFB1AEFF", material="PLA"):
    return {"id": slot, "tray_info_idx": preset, "tray_color": color, "tray_type": material}


def report(*, peer=None):
    return {"ams": [{"id": 0, "tray": [peer if peer is not None else tray(3)]}, {"id": 1, "tray": [tray(2)]}]}


def status(printer_id, raw, *, model="X1C", sides=None):
    state = SimpleNamespace(connected=True, ams_filament_backup=True, ams_extruder_map=sides or {}, raw_data=raw)
    stack = ExitStack()
    stack.enter_context(patch("backend.app.services.printer_manager.printer_manager.get_status", return_value=state))
    stack.enter_context(patch("backend.app.services.printer_manager.printer_manager.get_model", return_value=model))
    return stack


@pytest.fixture
async def setup(db_session, printer_factory, tmp_path):
    printer = await printer_factory(model="X1C")
    archive = await _setup_archive_3mf(
        db_session, tmp_path, [{"id": "1", "type": "PLA", "color": "#AFB1AE", "used_g": "194.0"}]
    )
    for unit, slot, used, preset in [(1, 2, 857.52, "PFUS-custom"), (0, 3, 0, "GFA10")]:
        spool = await _spool(db_session, label_weight=1000, weight_used=used, color="#AFB1AE", slicer_filament=preset)
        await _assign(db_session, printer_id=printer.id, spool_id=spool.id, ams_id=unit, tray_id=slot)
    item = await _queue_item(db_session, printer_id=printer.id, archive=archive, ams_mapping=[6])
    return printer, item


@pytest.mark.parametrize(
    "peer,short",
    [
        (tray(3), False),
        (tray(3, color="000000FF"), True),
        (tray(3, preset=""), True),
        (tray(3, material=""), True),
    ],
)
async def test_dispatch_uses_reported_identity_and_occupied_slots(db_session, setup, peer, short):
    printer, item = setup
    with status(printer.id, report(peer=peer)):
        result = await compute_deficit_for_queue_item(db_session, item)
    assert bool(result) is short
    if short:
        assert [(d.ams_id, d.tray_id) for d in result] == [(1, 2)]


async def test_ui_and_dispatch_share_keys_from_one_snapshot(db_session, setup):
    printer, item = setup
    with status(printer.id, report()):
        slots = {s.global_tray_id: s for s in await build_slot_materials(db_session, printer.id)}
        assert slots[3].material_key == slots[6].material_key
        with patch(
            "backend.app.services.filament_deficit._live_tray_keys", side_effect=[{3: "first", 6: "first"}]
        ) as keys:
            assert await compute_deficit_for_queue_item(db_session, item) == []
        keys.assert_called_once_with(printer.id)


async def test_reported_equal_material_cannot_cross_nozzles(db_session, setup):
    printer, item = setup
    with status(printer.id, report(), model="H2D", sides={"0": 0, "1": 1}):
        assert await compute_deficit_for_queue_item(db_session, item)


async def test_spoolman_uses_live_identity_without_merging_catalog_entries(db_session, printer_factory):
    printer = await printer_factory(model="X1C")
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    for unit, slot, sid in [(0, 3, 68), (1, 2, 69)]:
        db_session.add(SpoolmanSlotAssignment(printer_id=printer.id, ams_id=unit, tray_id=slot, spoolman_spool_id=sid))
    await db_session.commit()
    client = AsyncMock()
    client.get_spool.side_effect = lambda sid: {"id": sid, "remaining_weight": 500, "filament": {"id": sid}}
    with status(printer.id, report()), patch("backend.app.services.spoolman.get_spoolman_client", return_value=client):
        slots = await build_slot_materials(db_session, printer.id)
    assert len(slots) == 2 and slots[0].material_key == slots[1].material_key


def test_setting_and_rfid_ids_have_the_same_fallback_identity():
    a = SimpleNamespace(slicer_filament="GFA10", rgba="AFB1AEFF")
    b = SimpleNamespace(slicer_filament="GFSA10_02", rgba="#AFB1AE")
    assert _material_identity_internal(a) == _material_identity_internal(b)


def test_raw_nested_units_ht_and_malformed_entries():
    raw = {
        "ams": {
            "ams": [
                None,
                {"id": "bad", "tray": [tray(0)]},
                {"id": 128, "tray": [None, tray(0)]},
                {"id": 0, "tray": "bad"},
            ]
        }
    }
    with status(1, raw):
        assert _live_tray_keys(1) == {128: "preset:GFA10|color:AFB1AE"}


async def test_unknown_occupancy_and_external_spools_remain_outside_backup_pool(db_session, setup):
    printer, _ = setup
    with status(printer.id, {"vt_tray": tray(254)}):
        assert await build_slot_materials(db_session, printer.id) == []
