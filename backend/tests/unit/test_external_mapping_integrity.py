"""Capture real external targets and never charge an explicitly unfed slot."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.spoolman_tracking import _resolve_global_tray_id
from backend.app.services.usage_tracker import _track_from_3mf


@pytest.mark.parametrize(
    "model,details,want",
    [
        ("H2D", [{"ams_id": 255, "slot_id": 0}], [255]),
        ("H2D", [{"ams_id": 254, "slot_id": 0}], [254]),
        ("H2S", [{"ams_id": 255, "slot_id": 0}], [254]),
        ("X1C", [{"ams_id": 255, "slot_id": 255}], [-1]),
        ("X1C", None, [-1]),
    ],
)
def test_request_capture_preserves_external_target_and_unmapped(model, details, want):
    client = BambuMQTTClient("10.0.0.7", "MAPPING", "12345678", model=model)
    client._handle_request_message({"print": {"command": "project_file", "ams_mapping": [-1], "ams_mapping2": details}})
    assert client._captured_ams_mapping == want


def test_spoolman_unfed_slot_does_not_resolve_to_either_external_spool():
    assert _resolve_global_tray_id(2, [0, -1], {0: {}, 254: {}, 255: {}}) == -1


@pytest.mark.parametrize("details,want", [(None, None), ([{"ams_id": 255, "slot_id": 255}], [-1])])
def test_callbacks_distinguish_legacy_mapping_from_explicit_unfed(details, want):
    client = BambuMQTTClient("10.0.0.7", "MAPPING", "12345678", model="X1C")
    events = []
    client.on_print_start = events.append
    client.on_print_complete = events.append
    client._process_message({"print": {"gcode_state": "IDLE"}})
    client._handle_request_message({"print": {"command": "project_file", "ams_mapping": [-1], "ams_mapping2": details}})
    client._process_message({"print": {"gcode_state": "RUNNING", "gcode_file": "test.3mf"}})
    client._process_message({"print": {"gcode_state": "FINISH"}})
    assert len(events) == 2
    assert [event["ams_mapping"] for event in events] == [want, want]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mapping,expected_ids,expected_weights,expected_cost",
    [
        ([0, -1], [1], (110, 200), 0.2),
        ([255, -1], [2], (100, 210), 0.4),
        ([-1, -1], [], (100, 200), None),
    ],
)
async def test_unmapped_slot_does_not_change_stock_or_cost(
    db_session, printer_factory, mapping, expected_ids, expected_weights, expected_cost
):
    printer = await printer_factory()
    ams = Spool(material="PLA", weight_used=100, cost_per_kg=20, label_weight=1000)
    external = Spool(material="ABS", weight_used=200, cost_per_kg=40, label_weight=1000)
    db_session.add_all([ams, external])
    await db_session.flush()
    db_session.add_all(
        [
            SpoolAssignment(printer_id=printer.id, ams_id=0, tray_id=0, spool_id=ams.id),
            SpoolAssignment(printer_id=printer.id, ams_id=255, tray_id=1, spool_id=external.id),
        ]
    )
    await db_session.commit()
    state = SimpleNamespace(
        raw_data={
            "ams": [{"id": 0, "tray": [{"id": 0, "tray_type": "PLA"}]}],
            "vt_tray": [{"id": 255, "tray_type": "ABS"}],
        },
        tray_change_log=[],
        tray_now=255,
        last_loaded_tray=-1,
        progress=100,
    )
    usage = [{"slot_id": 1, "used_g": 10}, {"slot_id": 2, "used_g": 5}]
    with patch("backend.app.utils.threemf_tools.extract_filament_usage_from_3mf", return_value=usage):
        results = await _track_from_3mf(
            printer_id=printer.id,
            archive_id=None,
            status="completed",
            print_name="Mapping",
            handled_trays=set(),
            printer_manager=SimpleNamespace(get_status=lambda _: state),
            db=db_session,
            ams_mapping=mapping,
            threemf_path=Path("fixture.3mf"),
        )
    assert [r["spool_id"] for r in results] == expected_ids
    assert (ams.weight_used, external.weight_used) == expected_weights
    if results:
        assert results[0]["cost"] == expected_cost
