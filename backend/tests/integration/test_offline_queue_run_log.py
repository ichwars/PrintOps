"""One run survives offline cancellation, reconnects and later corrections."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from backend.app import main
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.print_completion_archive import find_completion_archive
from backend.app.services.print_log import write_log_entry

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("shared", [False, True])
async def test_offline_stop_logs_unknown_usage_and_protects_another_printers_run(
    shared, monkeypatch, async_client, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    other = await printer_factory()
    started = datetime(2026, 11, 10, 12)
    archive = await archive_factory(printer.id, with_run=False, status="printing", started_at=started)
    item = PrintQueueItem(printer_id=printer.id, archive_id=archive.id, status="printing", expected_parts=4)
    db_session.add(item)
    if shared:
        db_session.add(PrintQueueItem(printer_id=other.id, archive_id=archive.id, status="printing"))
    await db_session.commit()
    monkeypatch.setattr(main, "_user_stopped_printers", set())
    monkeypatch.setattr(main.printer_manager, "stop_print", lambda _: False)
    monkeypatch.setattr(main.ws_manager, "send_archive_updated", AsyncMock())
    event = AsyncMock()
    monkeypatch.setattr(main.mqtt_relay, "on_run_event", event)
    response = await async_client.post(f"/api/v1/queue/{item.id}/stop")
    assert response.status_code == 200, response.text
    await db_session.refresh(archive)
    assert archive.status == ("printing" if shared else "cancelled")
    rows = (await db_session.scalars(select(PrintLogEntry))).all()
    assert len(rows) == 1
    run = rows[0]
    assert run.status == "cancelled" and run.failure_reason == "userCancelled"
    event.assert_awaited_once()
    phase, published, target = event.await_args.args
    assert (phase, published.id, target.id) == ("completed", run.id, printer.id)
    assert run.duration_seconds == 0 and run.duration_unmeasured is True
    assert run.filament_used_grams is None and run.cost is None
    assert run.quantity == 4 and run.queue_item_id == item.id
    corrected = await write_log_entry(
        db_session,
        archive_id=archive.id,
        printer_id=printer.id,
        started_at=started,
        status="completed",
        completed_at=started + timedelta(hours=1),
        filament_used_grams=20,
        cost=0.4,
    )
    await db_session.commit()
    assert corrected.id == run.id and corrected.quantity == 4 and corrected.queue_item_id == item.id
    assert corrected.failure_reason is None and corrected.filament_used_grams == 20


async def test_same_outcome_preserves_usage_edits_and_quality_but_real_time_replaces_an_estimate(
    db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, quantity=2)
    started = datetime(2026, 11, 10, 12, tzinfo=timezone(timedelta(hours=2)))
    kwargs = {
        "db": db_session,
        "archive_id": archive.id,
        "printer_id": printer.id,
        "started_at": started,
        "status": "completed",
    }
    run = await write_log_entry(**kwargs, completed_at=started + timedelta(hours=1), cost=0.4, duration_unmeasured=True)
    run.good_quantity, run.reject_quantity = 1, 1
    run.user_verdict = "mixed"
    run.energy_cost = 0.1
    archive.quantity = 99
    await db_session.commit()
    again = await write_log_entry(**kwargs, completed_at=started + timedelta(hours=2), cost=999)
    await db_session.commit()
    assert again.id == run.id and again.duration_seconds == 7200 and again.duration_unmeasured is None
    assert again.cost == 0.4 and again.energy_cost == 0.1
    assert again.quantity == 2 and again.good_quantity == 1 and again.reject_quantity == 1
    assert again.started_at == datetime(2026, 11, 10, 10)


@pytest.mark.parametrize("separation", ["printer", "start", "missing"])
async def test_unrelated_or_unidentified_runs_never_merge(separation, db_session, printer_factory, archive_factory):
    printer = await printer_factory()
    other = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False)
    started = datetime(2026, 11, 10, 12)
    first = await write_log_entry(
        db_session, archive_id=archive.id, printer_id=printer.id, started_at=started, status="completed"
    )
    second = await write_log_entry(
        db_session,
        archive_id=archive.id,
        printer_id=other.id if separation == "printer" else printer.id,
        started_at=None
        if separation == "missing"
        else started + timedelta(seconds=1)
        if separation == "start"
        else started,
        status="completed",
    )
    assert first is not second


@pytest.mark.parametrize("reported", ["Clip", "Clip.gcode.3mf", "CLIP"])
async def test_untracked_completion_uses_literal_names_and_skips_deleted_rows(
    reported, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    target = await archive_factory(
        printer.id, with_run=False, status="printing", print_name="Clip", filename="Clip.gcode.3mf"
    )
    await archive_factory(
        printer.id, with_run=False, status="printing", print_name="Cable Clip", filename="Cable Clip.3mf"
    )
    await archive_factory(printer.id, with_run=False, status="printing", print_name="Clip", deleted_at=datetime.now())
    assert await find_completion_archive(db_session, printer.id, {"subtask_name": reported}) is target


@pytest.mark.parametrize("current", ["target-id", "other-id"])
async def test_completion_id_overrides_names_and_never_accepts_a_positive_conflict(
    current, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    target = await archive_factory(
        printer.id, with_run=False, status="printing", subtask_id="target-id", print_name="Clip"
    )
    found = await find_completion_archive(db_session, printer.id, {"subtask_name": "Clip", "subtask_id": current})
    assert (found is target) is (current == "target-id")
