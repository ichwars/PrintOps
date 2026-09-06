"""Plate-scoped chamber preheat regression coverage for issue #139."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.print_scheduler import PrintScheduler

TARGETS = {"PLA": 0, "PETG": 0, "ASA": 45, "PA": 50, "DEFAULT": 0}
PLA_TRAY = 1
ASA_TRAY = 2


@pytest.fixture
def scheduler():
    return PrintScheduler()


def _item(mapping=None, **overrides):
    values = {
        "id": 139,
        "ams_mapping": mapping,
        "preheat_override": "inherit",
        "preheat_chamber_target_override": None,
        "plate_id": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _state(*, ams=None, vt_tray=None, bed=60.0, chamber=50.0):
    raw_data = {}
    if ams is not None:
        raw_data["ams"] = ams
    if vt_tray is not None:
        raw_data["vt_tray"] = vt_tray
    return SimpleNamespace(
        raw_data=raw_data,
        temperatures={"bed": bed, "chamber": chamber},
        airduct_mode=1,
    )


def _mixed_ams():
    return [
        {
            "id": "0",
            "tray": [
                {"id": "0", "tray_type": "PETG Pro"},
                {"id": "1", "tray_type": "PLA"},
                {"id": "2", "tray_type": "ASA"},
            ],
        }
    ]


def _derive(scheduler, state, item, *, model="P2S"):
    with patch("backend.app.services.print_scheduler.printer_manager") as manager:
        manager.get_status.return_value = state
        return scheduler._derive_chamber_target(SimpleNamespace(id=7, model=model), TARGETS, item)


def test_fixed_printer_pla_job_ignores_parked_asa(scheduler):
    mapping = json.dumps([-1, -1, -1, PLA_TRAY])
    assert _derive(scheduler, _state(ams=_mixed_ams()), _item(mapping)) == 0


@pytest.mark.asyncio
async def test_preheat_stage_uses_the_assigned_items_mapping(scheduler):
    item = _item("[1]", preheat_override="on", plate_id=None)
    client = MagicMock()
    client.set_bed_temperature = MagicMock(return_value=True)
    client.set_chamber_temperature = MagicMock(return_value=True)
    client.set_airduct_mode = MagicMock(return_value=True)

    with (
        patch.object(scheduler, "_get_int_setting", AsyncMock(return_value=0)),
        patch.object(scheduler, "_get_setting", AsyncMock(return_value=None)),
        patch("backend.app.services.print_scheduler.printer_manager") as manager,
        patch("backend.app.services.print_scheduler.asyncio.sleep", AsyncMock()),
    ):
        manager.get_status.return_value = _state(ams=_mixed_ams())
        manager.get_client.return_value = client
        await scheduler._preheat_and_soak(
            MagicMock(),
            item,
            SimpleNamespace(id=7, model="H2D"),
            SimpleNamespace(bed_temperature=60),
        )

    client.set_bed_temperature.assert_called_once_with(60)
    client.set_chamber_temperature.assert_not_called()


def test_model_assigned_high_temperature_job_still_preheats(scheduler):
    mapping = json.dumps([-1, ASA_TRAY])
    assert _derive(scheduler, _state(ams=_mixed_ams()), _item(mapping), model="H2D") == 45


def test_multi_material_job_uses_maximum_of_only_mapped_trays(scheduler):
    mapping = json.dumps([PLA_TRAY, ASA_TRAY])
    assert _derive(scheduler, _state(ams=_mixed_ams()), _item(mapping)) == 45


@pytest.mark.parametrize("mapping", [None, "", "[-1, -1]", "[null]", "[]", "not-json", '{"tray": 1}'])
def test_unknown_mapping_conservatively_scans_loaded_ams(scheduler, mapping):
    assert _derive(scheduler, _state(ams=_mixed_ams()), _item(mapping)) == 45


def test_regular_and_ams_ht_global_ids_match_dispatch_mapping(scheduler):
    ams = _mixed_ams() + [
        {"id": 1, "tray": [{"id": 2, "tray_type": "PA"}]},
        {"id": 128, "tray": [{"id": 0, "tray_type": "ASA"}]},
    ]
    assert _derive(scheduler, _state(ams=ams), _item("[6]")) == 50
    assert _derive(scheduler, _state(ams=ams), _item("[128]")) == 45
    assert _derive(scheduler, _state(ams=ams), _item("[1]")) == 0


def test_external_spool_is_used_only_when_mapping_names_it(scheduler):
    state = _state(
        ams=[{"id": 0, "tray": [{"id": 0, "tray_type": "PLA"}]}],
        vt_tray=[{"id": 254, "tray_type": "ASA"}],
    )
    assert _derive(scheduler, state, _item("[254]")) == 45
    assert _derive(scheduler, state, _item("[0]")) == 0
    assert _derive(scheduler, state, _item(None)) == 0


def test_selected_cross_model_variant_supplies_its_own_mapping(scheduler):
    item = _item("[2]")
    item.library_file_id = 1
    item.library_file = SimpleNamespace(id=1)
    item.archive_id = None
    item.archive = None
    item.target_model = "H2S"
    item.nozzle_mapping = None
    item.filament_overrides = None
    item.required_filament_types = None
    item.print_time_seconds = 10
    variant = SimpleNamespace(
        library_file_id=2,
        library_file=SimpleNamespace(id=2),
        target_model="H2C",
        plate_id=3,
        ams_mapping="[1]",
        nozzle_mapping="[0]",
        filament_overrides=None,
        required_filament_types='["PLA"]',
        print_time_seconds=20,
    )

    scheduler._resolve_variant(item, SimpleNamespace(variant=variant))

    assert item.plate_id == 3
    assert item.ams_mapping == "[1]"
    assert _derive(scheduler, _state(ams=_mixed_ams()), item, model="H2C") == 0


@pytest.mark.asyncio
async def test_explicit_zero_override_still_disables_mapped_asa(scheduler):
    item = _item("[2]", preheat_override="on", preheat_chamber_target_override=0)
    client = MagicMock()
    client.set_bed_temperature = MagicMock(return_value=True)
    client.set_chamber_temperature = MagicMock(return_value=True)
    client.set_airduct_mode = MagicMock(return_value=True)
    state = _state(ams=_mixed_ams())

    with (
        patch.object(scheduler, "_get_int_setting", AsyncMock(return_value=0)),
        patch("backend.app.services.print_scheduler.extract_bed_temperature_from_3mf", return_value=60),
        patch("backend.app.services.print_scheduler.printer_manager") as manager,
        patch("backend.app.services.print_scheduler.asyncio.sleep", AsyncMock()),
    ):
        manager.get_status.return_value = state
        manager.get_client.return_value = client
        await scheduler._preheat_and_soak(
            MagicMock(),
            item,
            SimpleNamespace(id=7, model="H2D"),
            SimpleNamespace(bed_temperature=60, file_path="archives/job.3mf"),
        )

    client.set_bed_temperature.assert_called_once_with(60)
    client.set_chamber_temperature.assert_not_called()
