"""Offline completions retain proven outcomes without inventing measured times."""

import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app import main
from backend.app.api.routes.archives_runs import _load_run_aggregates, compute_time_accuracy
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.print_log import write_log_entry
from backend.app.services.print_reconciliation import reconciled_end_time, reconciled_outcome, reconciliation_payload


@pytest.mark.parametrize(
    "terminal,stored,current,expected",
    [
        ("FINISH", "job", "job", "completed"),
        ("FAILED", "job", "job", "failed"),
        ("FINISH", "job", "other", "aborted"),
        ("FINISH", None, "0", "aborted"),
        ("FINISH", "0", "0", "aborted"),
        ("FINISH", "job", None, "aborted"),
        ("IDLE", "job", "job", "aborted"),
        ("RUNNING", "job", "job", "aborted"),
    ],
)
def test_success_requires_the_same_real_job(terminal, stored, current, expected):
    assert (
        reconciled_outcome(SimpleNamespace(subtask_id=stored), SimpleNamespace(state=terminal, subtask_id=current))
        == expected
    )


def estimate_file(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Metadata/slice_info.config",
            '<config><plate><metadata key="index" value="1"/>'
            '<metadata key="prediction" value="1800"/><filament id="1" used_g="10" type="PLA"/></plate>'
            '<plate><metadata key="index" value="2"/>'
            '<metadata key="prediction" value="7200"/><filament id="1" used_g="30" type="PLA"/></plate></config>',
        )


@pytest.mark.parametrize("plate,expected", [(None, None), (1, 1800), (2, 7200)])
def test_estimate_uses_this_runs_plate_and_does_not_guess_a_multiplate_file(plate, expected, tmp_path):
    estimate_file(tmp_path / "job.3mf")
    started = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    archive = SimpleNamespace(id=1, started_at=started, plate_id=None, file_path="job.3mf", print_time_seconds=9000)
    result = reconciled_end_time(archive, started + timedelta(days=1), base_dir=tmp_path, plate_id=plate)
    assert result == (started.replace(tzinfo=None) + timedelta(seconds=expected) if expected else None)


def test_estimated_end_never_lies_after_reconnect(tmp_path):
    started = datetime(2026, 11, 9, 12)
    archive = SimpleNamespace(id=1, started_at=started, plate_id=None, file_path="", print_time_seconds=7200)
    now = started + timedelta(minutes=30)
    assert reconciled_end_time(archive, now, base_dir=tmp_path) == now


@pytest.mark.asyncio
async def test_reconnect_selects_the_queue_plate_and_excludes_deleted_archives(
    monkeypatch, test_engine, printer_factory, archive_factory, db_session, tmp_path
):
    printer = await printer_factory()
    estimate_file(tmp_path / "job.3mf")
    started = datetime(2026, 11, 9, 12)
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="job.3mf",
        status="printing",
        subtask_id="job",
        file_path="job.3mf",
        plate_id=1,
        started_at=started,
    )
    await archive_factory(printer.id, with_run=False, status="printing", deleted_at=started, subtask_id="job")
    db_session.add(PrintQueueItem(printer_id=printer.id, archive_id=archive.id, status="printing", plate_id=2))
    await db_session.commit()
    monkeypatch.setattr(main, "app_settings", SimpleNamespace(base_dir=tmp_path))
    monkeypatch.setattr(main, "async_session", async_sessionmaker(test_engine, expire_on_commit=False))
    state = SimpleNamespace(state="FINISH", connected=True, subtask_id="job", raw_data={}, progress=100, layer_num=300)
    monkeypatch.setattr(main.printer_manager, "get_status", lambda _: state)
    complete = AsyncMock()
    monkeypatch.setattr(main, "on_print_complete", complete)
    assert await main.reconcile_stale_active_prints(printer.id) == 1
    payload = complete.await_args.args[1]
    assert payload["status"] == "completed"
    assert payload["_reconciled_completed_at"] == started + timedelta(hours=2)
    assert payload["last_progress"] == 100 and payload["last_layer_num"] == 300


@pytest.mark.asyncio
async def test_failed_offline_payload_carries_the_printers_errors(tmp_path):
    archive = SimpleNamespace(subtask_id="job", filename="job.3mf", print_name="Job")
    error = SimpleNamespace(code="HMS", attr=1, module=2, severity=1, description="Fault", full_code="07008029")
    state = SimpleNamespace(state="FAILED", subtask_id="job", raw_data={}, hms_errors=[error], progress=50)
    payload = await reconciliation_payload(archive, state, datetime.now(timezone.utc), base_dir=tmp_path)
    assert payload["status"] == "failed" and payload["hms_errors"][0]["description"] == "Fault"
    assert "_reconciled_completed_at" not in payload


@pytest.mark.asyncio
async def test_estimated_duration_counts_in_totals_but_not_accuracy(
    async_client, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    started = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    archive = await archive_factory(
        printer.id,
        with_run=False,
        status="completed",
        print_time_seconds=3600,
        started_at=started,
        completed_at=started + timedelta(hours=1),
    )
    run = await write_log_entry(
        db_session,
        archive_id=archive.id,
        printer_id=printer.id,
        status="completed",
        started_at=started,
        completed_at=started + timedelta(hours=1),
        duration_unmeasured=True,
    )
    await db_session.commit()
    assert run.duration_seconds == 3600 and run.duration_unmeasured
    aggregate = await _load_run_aggregates(db_session, [archive.id])
    assert aggregate[archive.id]["unmeasured_run_count"] == 1
    assert compute_time_accuracy(archive, aggregate[archive.id])["time_accuracy"] is None
    response = await async_client.get("/api/v1/archives/stats")
    assert response.status_code == 200, response.text
    assert response.json()["total_print_time_hours"] == 1
    assert response.json()["average_time_accuracy"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("run_plate,grams,cost", [(None, 10, 0.2), (2, 30, 0.6)])
async def test_real_completion_pipeline_stores_the_estimated_end_and_unmeasured_run(
    run_plate, grams, cost, monkeypatch, test_engine, db_session, printer_factory, archive_factory, tmp_path
):
    from sqlalchemy import select

    from backend.app.core import database
    from backend.app.models.print_log import PrintLogEntry
    from backend.app.services import print_sd_cleanup, usage_tracker

    printer = await printer_factory()
    estimate_file(tmp_path / "job.3mf")
    monkeypatch.setattr(main, "app_settings", SimpleNamespace(base_dir=tmp_path, archive_dir=tmp_path / "archives"))
    started = datetime(2026, 11, 9, 12)
    ended = started + timedelta(hours=1)
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="job.3mf",
        status="printing",
        started_at=started,
        file_path="job.3mf",
        plate_id=1,
        filament_used_grams=10,
        cost=0.2,
    )
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(main, "async_session", sessions)
    monkeypatch.setattr(database, "async_session", sessions)
    monkeypatch.setattr(main, "_active_prints", {(printer.id, "job.3mf"): archive.id})
    monkeypatch.setattr(main, "_expected_prints", {})
    monkeypatch.setattr(main, "_timelapse_baselines", {})
    monkeypatch.setattr(main, "_print_ams_mappings", {})
    monkeypatch.setattr(main, "_print_plate_ids", {})
    monkeypatch.setattr(main, "_user_stopped_printers", set())
    session = SimpleNamespace(plate_id=run_plate) if run_plate is not None else None
    monkeypatch.setattr(main, "prepare_print_completion", AsyncMock(return_value=(session, False)))
    monkeypatch.setattr(main.print_provenance, "resolve_completed_print_owner", AsyncMock(return_value=False))
    monkeypatch.setattr(main.print_provenance, "discard_print_session", AsyncMock())
    monkeypatch.setattr(main, "settle_archive_cost_estimate", AsyncMock())
    monkeypatch.setattr(main, "spawn_background_task", lambda coro, **kwargs: coro.close())
    monkeypatch.setattr(print_sd_cleanup, "cleanup_after_print", AsyncMock())
    monkeypatch.setattr(usage_tracker, "on_print_complete", AsyncMock(return_value=[]))
    for method in ("get_status", "get_client", "get_current_print_user", "get_printer"):
        monkeypatch.setattr(main.printer_manager, method, lambda *args: None)
    monkeypatch.setattr(main.printer_manager, "set_awaiting_plate_clear", lambda *args: None)
    monkeypatch.setattr(main.printer_manager, "clear_current_print_user", lambda *args: None)
    for method in ("send_print_complete", "send_archive_updated", "broadcast"):
        monkeypatch.setattr(main.ws_manager, method, AsyncMock())
    for method in ("on_print_complete", "on_archive_updated"):
        monkeypatch.setattr(main.mqtt_relay, method, AsyncMock())
    await main.on_print_complete(
        printer.id,
        {
            "status": "completed",
            "filename": "job.3mf",
            "_reconciled": True,
            "_reconciled_completed_at": ended,
        },
    )
    await db_session.refresh(archive)
    run = await db_session.scalar(select(PrintLogEntry).where(PrintLogEntry.archive_id == archive.id))
    assert archive.status == "completed" and archive.completed_at == ended and archive.failure_reason is None
    assert run is not None and run.status == "completed" and run.duration_seconds == 3600
    assert run.duration_unmeasured is True
    assert run.filament_used_grams == grams and run.cost == cost
