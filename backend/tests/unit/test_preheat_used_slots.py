"""The actual selected plate must retain the same chamber target after handoff."""

import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.preheat_chamber import chamber_target_for_plate
from backend.app.services.print_scheduler import PrintScheduler


def sliced_plates(path, *, used_second=0, two_plates=True):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Metadata/project_settings.config",
            json.dumps({"curr_bed_type": "Textured PEI Plate", "textured_plate_temp_initial_layer": [60, 60]}),
        )
        next_plate = (
            '<plate><metadata key="index" value="2"/><metadata key="curr_bed_type" value="Textured PEI Plate"/>'
            '<filament id="2" used_g="20" type="PA"/></plate>'
            if two_plates
            else ""
        )
        archive.writestr(
            "Metadata/slice_info.config",
            '<config><plate><metadata key="index" value="1"/>'
            '<metadata key="curr_bed_type" value="Textured PEI Plate"/>'
            '<filament id="1" used_g="20" type="ASA"/>'
            f'<filament id="2" used_g="{used_second}" type="PA"/></plate>{next_plate}</config>',
        )


@pytest.fixture
def stage(tmp_path):
    path = tmp_path / "plates.3mf"
    sliced_plates(path)
    item = SimpleNamespace(
        id=139,
        ams_mapping="[0, 1]",
        plate_id=1,
        use_ams=True,
        preheat_override="on",
        preheat_chamber_target_override=None,
    )
    state = SimpleNamespace(
        state="FINISH",
        connected=True,
        temperatures={"bed": 60, "chamber": 60},
        airduct_mode=0,
        raw_data={"ams": [{"id": 0, "tray": [{"id": 0, "tray_type": "ASA"}, {"id": 1, "tray_type": "PA"}]}]},
    )
    return SimpleNamespace(path=path, item=item, state=state)


async def preheat(ctx):
    scheduler = PrintScheduler()
    client = MagicMock()
    client.set_bed_temperature.return_value = True
    client.set_chamber_temperature.return_value = True
    with (
        patch.object(scheduler, "_get_int_setting", AsyncMock(return_value=0)),
        patch.object(scheduler, "_get_setting", AsyncMock(return_value=None)),
        patch("backend.app.services.print_scheduler.printer_manager") as manager,
    ):
        manager.get_status.return_value = ctx.state
        manager.get_client.return_value = client
        await scheduler._preheat_and_soak(
            MagicMock(),
            ctx.item,
            SimpleNamespace(id=7, model="H2D"),
            SimpleNamespace(file_path=str(ctx.path), bed_temperature=60),
        )
    return client


@pytest.mark.asyncio
async def test_unused_but_mapped_pa_cannot_increase_real_asa_plate_target(stage):
    client = await preheat(stage)
    client.set_chamber_temperature.assert_called_once_with(45)


@pytest.mark.asyncio
async def test_selected_other_plate_uses_its_actual_consumed_pa_slot(stage):
    stage.item.plate_id = 2
    client = await preheat(stage)
    client.set_chamber_temperature.assert_called_once_with(50)


@pytest.mark.asyncio
async def test_ambiguous_plate_context_does_not_guess_chamber_or_airduct(stage):
    stage.item.plate_id = None
    client = await preheat(stage)
    client.set_bed_temperature.assert_called_once_with(60)
    client.set_chamber_temperature.assert_not_called()
    client.set_airduct_mode.assert_not_called()


@pytest.mark.asyncio
async def test_proven_single_plate_supports_implicit_selection(stage):
    sliced_plates(stage.path, two_plates=False)
    stage.item.plate_id = None
    client = await preheat(stage)
    client.set_chamber_temperature.assert_called_once_with(45)


@pytest.mark.asyncio
@pytest.mark.parametrize("mapping", [None, "invalid", "[]", "[-1, 1]", "[true, 1]", "[9, 1]"])
async def test_unknown_used_mapping_never_guesses_chamber_or_airduct(stage, mapping):
    stage.item.ams_mapping = mapping
    client = await preheat(stage)
    client.set_bed_temperature.assert_called_once_with(60)
    client.set_chamber_temperature.assert_not_called()
    client.set_airduct_mode.assert_not_called()


@pytest.mark.asyncio
async def test_unused_negative_mapping_does_not_hide_proven_used_slot(stage):
    stage.item.ams_mapping = "[0, -1]"
    client = await preheat(stage)
    client.set_chamber_temperature.assert_called_once_with(45)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [0, 52])
async def test_explicit_chamber_override_remains_authoritative_for_ambiguous_plate(stage, target):
    stage.item.plate_id = None
    stage.item.preheat_chamber_target_override = target
    stage.state.airduct_mode = 0 if target else 1
    client = await preheat(stage)
    if target:
        client.set_chamber_temperature.assert_called_once_with(target)
    else:
        client.set_chamber_temperature.assert_not_called()
        client.set_airduct_mode.assert_called_once_with("cooling")


@pytest.mark.asyncio
async def test_external_mapping_is_derived_only_from_consumed_slot(stage):
    stage.item.use_ams = False
    stage.item.ams_mapping = "[254, 1]"
    stage.state.raw_data["vt_tray"] = [{"id": 254, "tray_type": "ASA"}]
    client = await preheat(stage)
    client.set_chamber_temperature.assert_called_once_with(45)


@pytest.mark.asyncio
async def test_nonfinite_usage_cannot_be_treated_as_proven_unused_material(stage):
    sliced_plates(stage.path, used_second="nan")
    client = await preheat(stage)
    client.set_chamber_temperature.assert_not_called()
    client.set_airduct_mode.assert_not_called()


@pytest.mark.asyncio
async def test_absent_usage_file_skips_automatic_chamber(stage):
    stage.path.write_bytes(b"not sliced metadata")
    stage.item.plate_id = None
    client = await preheat(stage)
    client.set_bed_temperature.assert_called_once_with(60)
    client.set_chamber_temperature.assert_not_called()
    client.set_airduct_mode.assert_not_called()


def test_resolver_matches_hold_for_used_slot_despite_parked_mapping(stage):
    archive = SimpleNamespace(file_path=str(stage.path))
    assert chamber_target_for_plate(stage.state, {"ASA": 45, "PA": 50}, stage.item, archive) == 45


@pytest.mark.asyncio
@pytest.mark.parametrize("material", [None, "   ", 42])
async def test_unknown_consumed_material_skips_chamber_decisions(stage, material):
    stage.state.raw_data["ams"][0]["tray"][0]["tray_type"] = material
    client = await preheat(stage)
    client.set_chamber_temperature.assert_not_called()
    client.set_airduct_mode.assert_not_called()
