"""The same filament slot may use a different nozzle on another sliced plate."""

import io
import json
import zipfile

import pytest

from backend.app.utils.threemf_tools import extract_nozzle_mapping_from_3mf


@pytest.mark.parametrize(("plate_id", "expected"), [(1, {1: 0}), (2, {1: 1}), (9, None)])
def test_reads_only_the_selected_plates_nozzle(plate_id, expected):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr("Metadata/project_settings.config", json.dumps({"physical_extruder_map": [0, 1]}))
        zf.writestr(
            "Metadata/slice_info.config",
            """<config>
          <plate><metadata key="index" value="1"/><filament id="1" group_id="0"/></plate>
          <plate><metadata key="index" value="2"/><filament id="1" group_id="1"/></plate>
        </config>""",
        )
    with zipfile.ZipFile(data) as zf:
        assert extract_nozzle_mapping_from_3mf(zf, plate_id=plate_id) == expected


def test_project_fallback_keeps_only_slots_the_selected_plate_uses():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr(
            "Metadata/project_settings.config",
            json.dumps({"physical_extruder_map": [0, 1], "filament_nozzle_map": [0, 1]}),
        )
        zf.writestr(
            "Metadata/slice_info.config",
            """<config>
          <plate><metadata key="index" value="1"/><filament id="1"/></plate>
          <plate><metadata key="index" value="2"/><filament id="2"/></plate>
        </config>""",
        )
    with zipfile.ZipFile(data) as zf:
        assert extract_nozzle_mapping_from_3mf(zf, plate_id=2) == {2: 1}
