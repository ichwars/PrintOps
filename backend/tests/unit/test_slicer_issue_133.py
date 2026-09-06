import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.api.routes import slicer_presets as sp
from backend.app.api.routes.library import _run_slicer_with_fallback
from backend.app.schemas.slicer import PresetRef, SliceRequest
from backend.app.services.slice_output_check import slicer_output_error
from backend.app.services.slicer_profile_patch import patch_filament_colours

pytestmark = pytest.mark.unit


def _request(**kwargs) -> SliceRequest:
    return SliceRequest(
        printer_preset=PresetRef(source="standard", id="Bambu Lab P1S 0.4 nozzle"),
        process_preset=PresetRef(source="standard", id="0.20mm Standard @BBL X1C"),
        filament_presets=[PresetRef(source="standard", id="Generic PLA")],
        **kwargs,
    )


def _3mf(settings: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps(settings))
        archive.writestr("Metadata/plate_1.gcode", "G1 X0 Y0\n")
    return buffer.getvalue()


class TestBundledPresetData:
    @pytest.mark.asyncio
    async def test_passes_through_material_and_declared_printer_compatibility(self):
        sp._bundled_cache = None
        service = MagicMock()
        service.list_bundled_profiles = AsyncMock(
            return_value={
                "printer": [],
                "process": [
                    {
                        "name": "0.20mm Standard @BBL X1C",
                        "compatible_printers": ["Bambu Lab X1 Carbon 0.4 nozzle", "Bambu Lab P1S 0.4 nozzle"],
                    }
                ],
                "filament": [
                    {
                        "name": "Generic PETG",
                        "filament_type": "PETG",
                        "compatible_printers": "Bambu Lab P1S 0.4 nozzle",
                    }
                ],
            }
        )
        service.__aenter__ = AsyncMock(return_value=service)
        service.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(sp, "_resolve_slicer_api_url", AsyncMock(return_value="http://sidecar")),
            patch.object(sp, "SlicerApiService", return_value=service),
        ):
            slots = await sp._fetch_bundled_presets(MagicMock())

        assert slots["process"][0].compatible_printers == [
            "Bambu Lab X1 Carbon 0.4 nozzle",
            "Bambu Lab P1S 0.4 nozzle",
        ]
        assert slots["filament"][0].filament_type == "PETG"
        assert slots["filament"][0].compatible_printers == ["Bambu Lab P1S 0.4 nozzle"]


class TestFilamentColours:
    def test_request_normalises_hex_colours_and_preserves_empty_slots(self):
        assert _request(filament_colours=[" #e8b00c ", ""]).filament_colours == ["#E8B00C", ""]

    def test_request_rejects_an_invalid_colour_and_names_its_slot(self):
        with pytest.raises(ValidationError, match=r"filament_colours\[1\]"):
            _request(filament_colours=["#00AE42", "red"])

    def test_patches_each_profile_with_the_actual_requested_colour(self):
        profiles = [
            json.dumps({"name": "PLA", "type": "filament"}),
            json.dumps({"name": "PETG", "type": "filament"}),
        ]
        patched = patch_filament_colours(profiles, ["#112233", "#AABBCC"], b"")

        assert [json.loads(profile)["filament_colour"] for profile in patched] == [
            ["#112233"],
            ["#AABBCC"],
        ]

    def test_source_plate_colour_is_the_fallback_for_older_clients(self):
        source = _3mf({"filament_type": ["PLA"], "filament_colour": ["#ABCDEF"]})
        patched = patch_filament_colours([json.dumps({"name": "PLA"})], [], source)
        assert json.loads(patched[0])["filament_colour"] == ["#ABCDEF"]


class TestBadSidecarOutput:
    def test_missing_start_gcode_is_named_and_rejected(self):
        message = slicer_output_error(
            _3mf({"machine_start_gcode": "G28 X\n"}),
            export_3mf=True,
            printer_preset_name="Bambu Lab P1S 0.4 nozzle",
            filament_preset_names=["Generic PLA"],
        )
        assert message is not None
        assert "Bambu Lab P1S 0.4 nozzle" in message
        assert "not saved" in message

    def test_unresolved_filament_is_named_and_rejected(self):
        message = slicer_output_error(
            _3mf(
                {
                    "machine_start_gcode": "M1002 gcode_claim_action : 1\n",
                    "filament_vendor": ["Generic", "(Undefined)"],
                    "filament_ids": ["GFL96", ""],
                }
            ),
            export_3mf=True,
            printer_preset_name="Bambu Lab P1S 0.4 nozzle",
            filament_preset_names=["Generic PLA", "Custom PETG"],
        )
        assert message is not None
        assert "slot 2 (Custom PETG)" in message
        assert "PLA" in message
        assert "not saved" in message

    def test_resolved_output_passes(self):
        assert (
            slicer_output_error(
                _3mf(
                    {
                        "machine_start_gcode": "M1002 gcode_claim_action : 1\n",
                        "filament_vendor": ["Generic"],
                        "filament_ids": ["GFL96"],
                    }
                ),
                export_3mf=True,
                printer_preset_name="Bambu Lab P1S 0.4 nozzle",
                filament_preset_names=["Generic PLA"],
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_the_slice_wrapper_rejects_bad_output_before_a_caller_can_persist_it(self):
        from backend.app.services import slicer_api as slicer_api_module

        result = slicer_api_module.SliceResult(
            content=_3mf(
                {
                    "machine_start_gcode": "M1002 gcode_claim_action : 1\n",
                    "filament_vendor": ["(Undefined)"],
                    "filament_ids": [""],
                }
            ),
            print_time_seconds=10,
            filament_used_g=1.0,
            filament_used_mm=100.0,
        )
        service = MagicMock()
        service.slice_with_profiles = AsyncMock(return_value=result)
        service.close = AsyncMock()

        async def setting(_db, key):
            return {
                "preferred_slicer": "bambu_studio",
                "bambu_studio_api_url": "http://sidecar",
            }.get(key)

        with (
            patch("backend.app.api.routes.settings.get_setting", new=AsyncMock(side_effect=setting)),
            patch(
                "backend.app.services.preset_resolver.resolve_preset_ref",
                new=AsyncMock(return_value=json.dumps({"name": "resolved"})),
            ),
            patch.object(slicer_api_module, "SlicerApiService", return_value=service),
            pytest.raises(HTTPException) as exc,
        ):
            await _run_slicer_with_fallback(
                MagicMock(),
                model_bytes=b"solid cube\nendsolid cube\n",
                model_filename="cube.stl",
                request=_request(export_3mf=True),
            )

        assert exc.value.status_code == 502
        assert "Generic PLA" in exc.value.detail
        assert "not saved" in exc.value.detail
