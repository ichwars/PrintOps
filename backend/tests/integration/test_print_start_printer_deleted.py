"""Printer deletion races with real print-start state changes."""

import asyncio
import threading
import zipfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app import main
from backend.app.core.config import settings
from backend.app.models.active_print_session import ActivePrintSession
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services import bambu_ftp, usage_tracker
from backend.app.services.archive import ArchiveService
from backend.tests.integration.test_reprint_archive_lifecycle import quiet_start  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_deletion_during_plate_check_leaves_the_expected_archive_unchanged(
    quiet_start, async_client, db_session, printer_factory, archive_factory, monkeypatch
):
    printer, other = await printer_factory(), await printer_factory()
    printer_id = printer.id
    archive = await archive_factory(other.id, with_run=False, filename="fixture.3mf", status="completed")
    entered, release = asyncio.Event(), asyncio.Event()

    async def plate_check(*args, **kwargs):
        entered.set()
        await release.wait()

    monkeypatch.setattr(main, "check_print_start_plate", plate_check)
    main.register_expected_print(printer_id, archive.filename, archive.id, plate_id=1)
    start = asyncio.create_task(main.on_print_start(printer_id, {"filename": archive.filename}))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        assert (await async_client.delete(f"/api/v1/printers/{printer_id}")).status_code == 200
    finally:
        release.set()
        await asyncio.wait_for(start, timeout=5)

    await db_session.refresh(archive)
    assert (archive.printer_id, archive.status, archive.started_at) == (other.id, "completed", None)
    assert not main._active_prints and not main._expected_prints
    main._send_print_start_notification.assert_not_awaited()


async def test_archive_copy_is_removed_when_printer_is_deleted_before_insert(
    async_client, db_session, test_engine, printer_factory, monkeypatch, tmp_path
):
    from backend.app.utils import threemf_tools

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archives")
    source = tmp_path / "fixture.3mf"
    with zipfile.ZipFile(source, "w") as file:
        file.writestr("Metadata/plate_1.gcode", "G28")
    printer_id = (await printer_factory()).id
    parsing, release = threading.Event(), threading.Event()
    original = threemf_tools.extract_plate_estimates_from_3mf

    def parse(path):
        parsing.set()
        if not release.wait(timeout=10):
            raise TimeoutError("archive fixture was not released")
        return original(path)

    monkeypatch.setattr(threemf_tools, "extract_plate_estimates_from_3mf", parse)
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def write():
        async with sessions() as db:
            return await ArchiveService(db).archive_print(printer_id, source)

    start = asyncio.create_task(write())
    try:
        assert await asyncio.to_thread(parsing.wait, 5)
        assert list(settings.archive_dir.rglob("*.3mf"))
        assert (await async_client.delete(f"/api/v1/printers/{printer_id}")).status_code == 200
    finally:
        release.set()
        result = await asyncio.wait_for(start, timeout=5)
    assert result is None
    assert not list(settings.archive_dir.rglob("*.3mf"))
    assert await db_session.scalar(select(PrintArchive)) is None
    assert source.is_file()


async def test_late_start_work_retires_the_deleted_printers_runtime_state(
    quiet_start, async_client, db_session, printer_factory, archive_factory, monkeypatch
):
    printer_id = (await printer_factory()).id
    archive = await archive_factory(printer_id, with_run=False, filename="fixture.3mf")
    entered, release = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(usage_tracker, "_active_sessions", {})
    clear_3mf = MagicMock()
    monkeypatch.setattr(bambu_ftp, "clear_3mf_cache", clear_3mf)

    async def capture(*args, **kwargs):
        entered.set()
        await release.wait()
        usage_tracker._active_sessions[printer_id] = object()
        main._timelapse_baselines[printer_id] = {"fixture.avi"}

    monkeypatch.setattr(main, "_capture_timelapse_baseline_at_start", capture)
    main.register_expected_print(printer_id, archive.filename, archive.id, plate_id=1)
    start = asyncio.create_task(main.on_print_start(printer_id, {"filename": archive.filename}))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        response = await async_client.delete(f"/api/v1/printers/{printer_id}", params={"delete_archives": False})
        assert response.status_code == 200, response.text
    finally:
        release.set()
        await asyncio.wait_for(start, timeout=5)
    await db_session.refresh(archive)
    assert archive.printer_id is None and archive.status == "aborted"
    assert printer_id not in usage_tracker._active_sessions and printer_id not in main._timelapse_baselines
    assert clear_3mf.call_count == 2
    assert await db_session.get(ActivePrintSession, printer_id) is None


async def test_removing_one_printer_preserves_a_shared_file_and_the_other_open_run(
    async_client, db_session, printer_factory, archive_factory
):
    removed_id = (await printer_factory()).id
    other_id = (await printer_factory()).id
    start = datetime(2026, 11, 11, 10)
    archive = await archive_factory(removed_id, with_run=False, status="printing", started_at=start, plate_id=1)
    rows = [
        PrintLogEntry(archive_id=archive.id, printer_id=removed_id, status="printing", started_at=start, plate_id=1),
        PrintLogEntry(
            archive_id=archive.id,
            printer_id=other_id,
            status="printing",
            started_at=start - timedelta(minutes=1),
            plate_id=2,
            subtask_id="still-printing",
        ),
    ]
    item = PrintQueueItem(archive_id=archive.id, printer_id=other_id, status="printing", plate_id=2)
    db_session.add_all([*rows, item])
    await db_session.commit()

    response = await async_client.delete(f"/api/v1/printers/{removed_id}")
    assert response.status_code == 200, response.text
    await db_session.refresh(archive)
    assert (archive.printer_id, archive.status, archive.plate_id, archive.subtask_id) == (
        other_id,
        "printing",
        2,
        "still-printing",
    )
    await db_session.refresh(item)
    assert item.status == "printing"
    remaining = await db_session.scalars(
        select(PrintLogEntry)
        .where(PrintLogEntry.archive_id == archive.id)
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )
    assert [run.printer_id for run in remaining] == [other_id]
    assert (await printer_factory()).id != removed_id
