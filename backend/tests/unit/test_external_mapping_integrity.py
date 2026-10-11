"""Capture real external targets and never charge an explicitly unfed slot."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app.models.active_print_spoolman import ActivePrintSpoolman
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.spoolman_tracking import _resolve_global_tray_id
from backend.app.services.usage_tracker import PrintSession, _track_from_3mf, on_print_complete


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
    "mapping,expected_ids,expected_weights,expected_cost,split",
    [
        ([0, -1], [1], (110, 200), 0.2, False),
        ([255, -1], [2], (100, 210), 0.4, False),
        ([-1, -1], [], (100, 200), None, False),
        ([-1], [], (100, 200), None, True),
        (None, [2], (100, 210), 0.4, False),
    ],
)
async def test_unmapped_slot_does_not_change_stock_or_cost(
    db_session, printer_factory, mapping, expected_ids, expected_weights, expected_cost, split
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
        tray_change_log=[(0, 0), (255, 50)] if split else [],
        total_layers=100,
        tray_now=255,
        last_loaded_tray=-1,
        progress=100,
    )
    usage = [{"slot_id": 1, "used_g": 10}, {"slot_id": 2, "used_g": 5}]
    if split or mapping is None:
        usage = usage[:1]
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


@pytest.mark.asyncio
async def test_spoolman_split_cannot_charge_an_explicitly_unfed_slot(
    test_engine, db_session, printer_factory, archive_factory, monkeypatch
):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from backend.app.models.active_print_spoolman import ActivePrintSpoolman
    from backend.app.models.settings import Settings
    from backend.app.services import spoolman_tracking
    from backend.app.services.printer_manager import printer_manager

    printer = await printer_factory()
    archive = await archive_factory(printer.id)
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    db_session.add(
        ActivePrintSpoolman(
            printer_id=printer.id,
            archive_id=archive.id,
            slot_to_tray=[-1],
            filament_usage=[{"slot_id": 1, "used_g": 10}],
            ams_trays={"0": {"tray_uuid": "AAAA", "tray_type": "PLA"}, "1": {"tray_uuid": "BBBB", "tray_type": "PLA"}},
        )
    )
    await db_session.commit()
    consumed = {1: 0, 2: 0}

    async def find(tag):
        return {"id": 1 if tag == "AAAA" else 2, "filament": {"weight": 1000, "color_hex": "FF0000"}}

    async def use(spool_id, grams):
        consumed[spool_id] += grams

    async def get_client():
        return SimpleNamespace(find_spool_by_tag=find, use_spool=use)

    monkeypatch.setattr(spoolman_tracking, "async_session", async_sessionmaker(test_engine, expire_on_commit=False))
    monkeypatch.setattr(spoolman_tracking, "_get_spoolman_client_with_fallback", get_client)
    monkeypatch.setattr(
        printer_manager,
        "get_status",
        lambda _: SimpleNamespace(
            tray_change_log=[(0, 0), (1, 50)],
            total_layers=100,
            layer_num=100,
            raw_data={},
        ),
    )
    await spoolman_tracking.report_usage(printer.id, archive.id)
    assert consumed == {1: 0, 2: 0}


@pytest.mark.asyncio
async def test_explicit_all_unfed_mapping_cannot_charge_remain_fallback(db_session, printer_factory):
    printer = await printer_factory()
    spool = Spool(material="PLA", weight_used=100, label_weight=1000, cost_per_kg=20)
    db_session.add(spool)
    await db_session.flush()
    db_session.add(SpoolAssignment(printer_id=printer.id, spool_id=spool.id, ams_id=0, tray_id=0))
    await db_session.commit()
    session = PrintSession(
        printer_id=printer.id,
        print_name="Unfed",
        started_at=datetime.now(timezone.utc),
        ams_mapping=[-1],
        tray_remain_start={(0, 0): 80},
        tray_now_at_start=0,
        spool_assignments={(0, 0): spool.id},
    )
    state = SimpleNamespace(
        raw_data={"ams": [{"id": 0, "tray": [{"id": 0, "remain": 70}]}]},
        tray_now=0,
        tray_change_log=[],
        last_loaded_tray=0,
    )
    results = await on_print_complete(
        printer.id,
        {"status": "completed"},
        SimpleNamespace(get_status=lambda _: state),
        db_session,
        claimed_session=session,
        session_claimed=True,
    )
    assert results == []
    assert spool.weight_used == 100
