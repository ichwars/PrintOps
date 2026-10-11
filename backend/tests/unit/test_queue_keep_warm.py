"""Keep-warm needs proven compatible plate/filament metadata and bounded ownership."""

import json
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.services.queue_keep_warm import compatible_keep_warm_target


def sliced_file(path, *, bed=90, filament="ASA", plate=1, bed_type="Textured PEI Plate"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Metadata/project_settings.config",
            json.dumps(
                {
                    "curr_bed_type": bed_type,
                    "textured_plate_temp_initial_layer": [bed],
                    "hot_plate_temp_initial_layer": [bed],
                }
            ),
        )
        archive.writestr(
            "Metadata/slice_info.config",
            f'''<config><plate>
          <metadata key="index" value="{plate}"/>
          <metadata key="curr_bed_type" value="{bed_type}"/>
          <filament id="1" used_g="20" type="{filament}"/>
        </plate></config>''',
        )


@pytest.fixture
def compatible(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.services.queue_keep_warm.settings.base_dir", tmp_path)
    for name in ("previous.3mf", "next.3mf"):
        sliced_file(tmp_path / name)
    printer = SimpleNamespace(id=7, model="X1C")

    def item(identity, name, status):
        return SimpleNamespace(
            id=identity,
            printer_id=7,
            status=status,
            plate_id=1,
            ams_mapping="[0]",
            manual_start=False,
            scheduled_time=None,
            filament_short=False,
            preheat_override="inherit",
            preheat_chamber_target_override=None,
            gcode_injection=False,
            filament_overrides=None,
            auto_off_after=False,
            variants=[],
            completed_at=datetime.now(timezone.utc),
            archive=SimpleNamespace(
                file_path=name,
                filename=name,
                bed_type="Textured PEI Plate",
                sliced_for_model="X1C",
                printer_id=7,
                deleted_at=None,
                status="completed",
                subtask_id="finished-task",
            ),
        )

    previous = item(1, "previous.3mf", "completed")
    following = item(2, "next.3mf", "pending")
    state = SimpleNamespace(
        state="FINISH",
        connected=True,
        subtask_id="finished-task",
        temperatures={"bed": 88, "bed_target": 0, "chamber": 46},
        raw_data={"ams": [{"id": 0, "tray": [{"id": 0, "tray_type": "ASA"}, {"id": 1, "tray_type": "PA"}]}]},
    )
    return SimpleNamespace(printer=printer, previous=previous, next=following, state=state, path=tmp_path)


def candidate(ctx):
    return compatible_keep_warm_target(ctx.printer, ctx.previous, ctx.next, ctx.state, {"ASA": 45, "PA": 50})


def test_proven_same_plate_filament_and_live_warmth_are_eligible(compatible):
    assert candidate(compatible) == 90


@pytest.mark.parametrize("model", ["H2C", "H2D", "P1S", "A1", ""])
def test_unverified_model_path_stays_disabled(compatible, model):
    compatible.printer.model = model
    assert candidate(compatible) is None


@pytest.mark.parametrize("bed", [0, 70, 115])
def test_missing_different_or_excessive_actual_plate_temperature_is_ineligible(compatible, bed):
    sliced_file(compatible.path / "next.3mf", bed=bed)
    assert candidate(compatible) is None


def test_parked_pa_slot_does_not_inflate_asa_chamber_target(compatible):
    # Only ASA slot zero is mapped; unused PA must not change the decision.
    assert candidate(compatible) == 90


@pytest.mark.parametrize("mapping", [None, "[]", "[-1]", "[1]", "garbled"])
def test_unknown_or_different_used_filament_mapping_is_ineligible(compatible, mapping):
    compatible.next.ams_mapping = mapping
    assert candidate(compatible) is None


def test_slicer_material_mismatch_stays_disabled(compatible):
    sliced_file(compatible.path / "next.3mf", filament="ABS")
    assert candidate(compatible) is None


def test_no_bed_metadata_fallback_is_used(compatible):
    compatible.next.archive.bed_temperature = 100
    (compatible.path / "next.3mf").write_bytes(b"not a sliced project")
    assert candidate(compatible) is None


def test_real_selected_plate_type_beats_archive_first_plate_metadata(compatible):
    sliced_file(compatible.path / "next.3mf", bed_type="Smooth PEI Plate")
    assert compatible.next.archive.bed_type == compatible.previous.archive.bed_type
    assert candidate(compatible) is None


@pytest.mark.parametrize("plate", [None, 0, True, 2])
def test_missing_or_unproven_selected_plate_is_ineligible(compatible, plate):
    compatible.next.plate_id = plate
    assert candidate(compatible) is None


@pytest.mark.parametrize("field", ["gcode_injection", "filament_overrides", "variants"])
def test_changed_previous_print_source_cannot_prove_compatibility(compatible, field):
    setattr(compatible.previous, field, True)
    assert candidate(compatible) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("manual_start", True),
        ("gcode_injection", True),
        ("filament_short", True),
        ("preheat_override", "off"),
        ("filament_overrides", "[]"),
    ],
)
def test_ineligible_dispatch_options_do_not_heat(compatible, field, value):
    setattr(compatible.next, field, value)
    assert candidate(compatible) is None


@pytest.mark.parametrize(
    "change", ["cold_chamber", "cold_bed", "unknown_prior_job", "different_model", "deleted_source"]
)
def test_unknown_or_incompatible_session_does_not_heat(compatible, change):
    if change == "cold_chamber":
        compatible.state.temperatures["chamber"] = 20
    elif change == "cold_bed":
        compatible.state.temperatures["bed"] = 30
    elif change == "unknown_prior_job":
        compatible.state.subtask_id = "another-job"
    elif change == "different_model":
        compatible.next.archive.sliced_for_model = "P2S"
    else:
        compatible.next.archive.deleted_at = datetime.now(timezone.utc)
    assert candidate(compatible) is None


@pytest.mark.asyncio
async def test_keep_warm_setting_is_disabled_and_duration_bounded_by_default():
    from pydantic import ValidationError

    from backend.app.schemas.settings import AppSettings, AppSettingsUpdate

    assert not AppSettings().queue_keep_bed_warm
    assert AppSettings().queue_keep_warm_max_minutes == 10
    for minutes in (0, 31):
        with pytest.raises(ValidationError):
            AppSettingsUpdate(queue_keep_warm_max_minutes=minutes)


def test_p2s_same_verified_profiles_are_eligible(compatible):
    compatible.printer.model = "P2S"
    compatible.previous.archive.sliced_for_model = "P2S"
    compatible.next.archive.sliced_for_model = "P2S"
    assert candidate(compatible) == 90


def test_explicit_external_filament_mapping_can_prove_compatibility(compatible):
    compatible.state.raw_data["vt_tray"] = [{"id": 254, "tray_type": "ASA"}]
    compatible.previous.ams_mapping = compatible.next.ams_mapping = "[254]"
    compatible.previous.use_ams = compatible.next.use_ams = False
    assert candidate(compatible) == 90


@pytest.mark.parametrize("sliced_for", ["X1C", "", "P2S"])
def test_library_next_job_requires_its_parsed_model_and_real_plate(compatible, sliced_for):
    compatible.next.archive = None
    compatible.next.library_file = SimpleNamespace(
        deleted_at=None,
        file_type="3mf",
        file_metadata={"sliced_for_model": sliced_for},
        file_path="next.3mf",
        variant_target_model="X1C",  # A user's assertion is never model proof.
    )
    assert candidate(compatible) == (90 if sliced_for == "X1C" else None)


def test_disabled_ams_does_not_assume_a_mapped_ams_spool_is_used(compatible):
    compatible.next.use_ams = False
    assert candidate(compatible) is None


@pytest.mark.parametrize("temperature", [float("nan"), float("inf"), "invalid"])
def test_invalid_live_temperature_never_authorizes_heat(compatible, temperature):
    compatible.state.temperatures["chamber"] = temperature
    assert candidate(compatible) is None


def test_nonfinite_consumption_does_not_prove_an_extra_material_is_unused(compatible):
    from backend.tests.unit.test_preheat_used_slots import sliced_plates

    sliced_plates(compatible.path / "previous.3mf", two_plates=False)
    sliced_plates(compatible.path / "next.3mf", used_second="nan", two_plates=False)
    compatible.previous.ams_mapping = compatible.next.ams_mapping = "[0, 1]"
    assert candidate(compatible) is None
