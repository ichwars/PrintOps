"""A failed first run does not change the cost of printing the full file."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.services.usage_tracker import PrintSession, _active_sessions, on_print_complete
from backend.tests.unit.test_issue_131_archive_recovery import _make_3mf

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("status,expected", [("failed", 5.0), ("completed", 0.25)])
async def test_only_a_full_completed_run_reprices_the_archive(
    db_session, printer_factory, archive_factory, tmp_path, monkeypatch, status, expected
):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    _make_3mf(tmp_path / "print.3mf")
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id, file_path="print.3mf", filament_used_grams=12.5, cost=5.0, with_run=False
    )
    spool = Spool(material="PLA", label_weight=1000, cost_per_kg=20.0)
    db_session.add(spool)
    await db_session.flush()
    db_session.add(SpoolAssignment(spool_id=spool.id, printer_id=printer.id, ams_id=0, tray_id=0))
    await db_session.commit()
    _active_sessions[printer.id] = PrintSession(
        printer.id, "part", datetime.now(timezone.utc), tray_now_at_start=0, ams_mapping=[0], spool_change_log=[]
    )
    state = SimpleNamespace(
        progress=50,
        layer_num=50,
        total_layers=100,
        tray_now=0,
        last_loaded_tray=0,
        raw_data={"ams": [{"id": 0, "tray": [{"id": 0, "tray_type": "PLA", "remain": 70}]}]},
    )
    manager = SimpleNamespace(get_status=lambda pid: state)
    try:
        results = await on_print_complete(printer.id, {"status": status}, manager, db_session, archive_id=archive.id)
        assert results
        await db_session.refresh(archive)
        assert archive.cost == expected
    finally:
        _active_sessions.clear()
