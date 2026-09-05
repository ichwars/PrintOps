"""Active-print provenance must survive a process restart (issue #128)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.app.models.active_print_session import ActivePrintSession
from backend.app.models.printer import Printer
from backend.app.services.usage_tracker import (
    PrintSession,
    _active_sessions,
    clear_persisted_session,
    on_print_complete,
    persist_session,
    record_tray_change,
    restore_session,
)


@pytest.fixture(autouse=True)
def _clear_active_sessions():
    _active_sessions.clear()
    yield
    _active_sessions.clear()


@pytest.fixture
async def printer(db_session):
    row = Printer(
        name="Issue 128 printer",
        ip_address="192.168.0.10",
        access_code="1234",
        serial_number="ISSUE128",
    )
    db_session.add(row)
    await db_session.commit()
    return row


def _session(printer_id: int) -> PrintSession:
    return PrintSession(
        printer_id=printer_id,
        print_name="backup-test",
        started_at=datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc),
        tray_remain_start={(0, 2): 84, (0, 3): 100},
        tray_now_at_start=2,
        spool_assignments={(0, 2): 69, (0, 3): 68},
        ams_mapping=[2],
        plate_id=1,
    )


def _printer_manager_for_start():
    manager = MagicMock()
    manager.get_status.return_value = MagicMock(
        raw_data={
            "ams": {"ams": [{"id": 0, "tray": [{"id": 2, "remain": 84, "tray_type": "ABS"}]}]},
            "vt_tray": [],
        },
        tray_now=2,
        last_loaded_tray=2,
        tray_change_log=[(2, 0)],
    )
    return manager


@pytest.mark.asyncio
async def test_session_and_backup_log_round_trip_after_restart(db_session, printer):
    await persist_session(db_session, _session(printer.id), [(2, 0)])
    _active_sessions.clear()
    await record_tray_change(db_session, printer.id, 3, 675)

    tray_log = await restore_session(db_session, printer.id)

    assert tray_log == [[2, 0], [3, 675]]
    restored = _active_sessions[printer.id]
    assert restored.ams_mapping == [2]
    assert restored.plate_id == 1
    assert restored.spool_assignments == {(0, 2): 69, (0, 3): 68}
    assert restored.tray_remain_start == {(0, 2): 84, (0, 3): 100}
    assert restored.started_at.tzinfo is not None


@pytest.mark.asyncio
async def test_new_print_replaces_stale_session_and_clear_is_idempotent(db_session, printer):
    await persist_session(db_session, _session(printer.id), [(2, 0), (3, 675)])
    replacement = _session(printer.id)
    replacement.print_name = "repeat"
    replacement.ams_mapping = [5]

    await persist_session(db_session, replacement, [(5, 0)])

    rows = (await db_session.execute(select(ActivePrintSession))).scalars().all()
    assert len(rows) == 1
    assert await restore_session(db_session, printer.id) == [[5, 0]]
    assert _active_sessions[printer.id].print_name == "repeat"
    await clear_persisted_session(db_session, printer.id)
    await clear_persisted_session(db_session, printer.id)
    assert await restore_session(db_session, printer.id) is None


@pytest.mark.asyncio
async def test_completion_recovers_persisted_mapping_plate_and_assignments(db_session, printer):
    await persist_session(db_session, _session(printer.id), [(2, 0), (3, 675)])
    _active_sessions.clear()
    captured: dict = {}

    async def _capture_track(*args, **kwargs):
        captured.update(kwargs)
        return []

    with (
        patch("backend.app.api.routes.settings.get_setting", new_callable=AsyncMock, return_value=None),
        patch("backend.app.services.usage_tracker._track_from_3mf", side_effect=_capture_track),
    ):
        await on_print_complete(
            printer.id,
            {"status": "completed", "subtask_name": "backup-test"},
            MagicMock(),
            db_session,
            archive_id=312,
        )

    assert captured["plate_id"] == 1
    assert captured["ams_mapping"] == [2]
    assert captured["tray_now_at_start"] == 2
    assert captured["spool_assignments"] == {(0, 2): 69, (0, 3): 68}


@pytest.mark.asyncio
@pytest.mark.parametrize("spoolman_owns_usage", [False, True])
async def test_print_start_persists_provenance_for_both_inventory_modes(
    db_session,
    printer,
    spoolman_owns_usage,
):
    from backend.app.services.usage_tracker import on_print_start

    await on_print_start(
        printer.id,
        {"subtask_name": "backup-test", "ams_mapping": [2]},
        _printer_manager_for_start(),
        db=db_session,
        spoolman_owns_usage=spoolman_owns_usage,
    )

    row = await db_session.get(ActivePrintSession, printer.id)
    assert row is not None
    assert row.ams_mapping == [2]
    assert row.tray_change_log == [[2, 0]]
    assert (printer.id in _active_sessions) is (not spoolman_owns_usage)


@pytest.mark.asyncio
async def test_restart_restores_persisted_tray_history_onto_live_state(db_session, printer):
    from backend.app.services.active_print_provenance import restore_for_running_print

    await persist_session(db_session, _session(printer.id), [(2, 0)])
    _active_sessions.clear()
    state = SimpleNamespace(
        subtask_name="backup-test",
        tray_change_log=[(3, 675)],
        tray_now=3,
        layer_num=700,
        last_loaded_tray=-1,
    )

    with patch("backend.app.api.routes.settings.get_setting", new_callable=AsyncMock, return_value=None):
        await restore_for_running_print(printer.id, state, db_session, MagicMock())

    assert state.tray_change_log == [(2, 0), (3, 675)]
    assert state.last_loaded_tray == 3
    assert _active_sessions[printer.id].plate_id == 1


@pytest.mark.asyncio
async def test_restart_discards_stale_identity_and_seeds_current_tray(db_session, printer):
    from backend.app.services.active_print_provenance import restore_for_running_print

    stale = _session(printer.id)
    stale.print_name = "old-print"
    await persist_session(db_session, stale, [(2, 0)])
    state = SimpleNamespace(
        subtask_name="new-print",
        tray_change_log=[],
        tray_now=3,
        layer_num=700,
        last_loaded_tray=-1,
    )

    await restore_for_running_print(printer.id, state, db_session, MagicMock())

    assert printer.id not in _active_sessions
    assert await restore_session(db_session, printer.id) is None
    assert state.tray_change_log == [(3, 700)]
