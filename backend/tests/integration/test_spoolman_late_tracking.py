"""A late 3MF enriches tracking without inventing a new start snapshot."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.app.models.active_print_session import ActivePrintSession
from backend.app.models.active_print_spoolman import ActivePrintSpoolman
from backend.app.models.settings import Settings
from backend.app.services.spoolman_tracking import attach_recovered_3mf
from backend.tests.unit.test_issue_131_archive_recovery import _make_3mf

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "existing,may_start,owner,enabled,expected",
    [
        (True, True, None, True, True),
        (True, False, None, True, True),
        (False, True, None, True, True),
        (False, False, None, True, False),
        (False, True, False, True, False),
        (False, True, True, False, True),
        (False, True, None, False, False),
    ],
)
async def test_recovered_3mf_keeps_start_evidence_and_ownership(
    db_session, printer_factory, archive_factory, tmp_path, monkeypatch, existing, may_start, owner, enabled, expected
):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    _make_3mf(tmp_path / "print.3mf")
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False)
    db_session.add(Settings(key="spoolman_enabled", value=str(enabled).lower()))
    if owner is not None:
        db_session.add(ActivePrintSession(printer_id=printer.id, started_at=datetime.now(), spoolman_owns_usage=owner))
    snapshot = {"0-0": {"remain": 80, "tray_uuid": "old"}}
    if existing:
        db_session.add(
            ActivePrintSpoolman(
                printer_id=printer.id,
                archive_id=archive.id,
                ams_trays={},
                tray_remain_start=snapshot,
                tray_now_at_start=0,
                slot_to_tray=[0],
            )
        )
    await db_session.commit()
    manager = SimpleNamespace(get_status=lambda pid: SimpleNamespace(raw_data={}))
    await attach_recovered_3mf(printer.id, archive.id, "print.3mf", db_session, manager, may_start=may_start)
    from sqlalchemy import select

    row = (await db_session.execute(select(ActivePrintSpoolman))).scalar_one_or_none()
    if not expected:
        assert row is None
        return
    assert row.filament_usage[0]["used_g"] == 12.5
    if existing:
        assert (row.tray_remain_start, row.slot_to_tray, row.ams_trays) == (snapshot, [0], {})
    else:
        assert row.tray_remain_start is None


async def test_already_tracked_grams_are_not_replaced(
    db_session, printer_factory, archive_factory, tmp_path, monkeypatch
):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    _make_3mf(tmp_path / "print.3mf")
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False)
    usage = [{"slot_id": 1, "used_g": 7.0}]
    row = ActivePrintSpoolman(printer_id=printer.id, archive_id=archive.id, ams_trays={}, filament_usage=usage)
    db_session.add(row)
    await db_session.commit()
    await attach_recovered_3mf(printer.id, archive.id, "print.3mf", db_session, None)
    assert row.filament_usage == usage
