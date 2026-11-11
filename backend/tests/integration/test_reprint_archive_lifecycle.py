"""A fresh run clears display state and never revives a deleted source row."""

import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app import main
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services import bambu_ftp, fallback_archive_recovery

pytestmark = pytest.mark.asyncio


@pytest.fixture
def quiet_start(monkeypatch, test_engine, tmp_path):
    monkeypatch.setattr(main, "async_session", async_sessionmaker(test_engine, expire_on_commit=False))
    monkeypatch.setattr(main, "app_settings", SimpleNamespace(base_dir=tmp_path, archive_dir=tmp_path / "archives"))
    for name in (
        "_expected_prints",
        "_expected_print_registered_at",
        "_expected_print_creators",
        "_active_prints",
        "_print_ams_mappings",
        "_print_plate_ids",
        "_timelapse_baselines",
        "_bed_cool_waiters",
    ):
        monkeypatch.setattr(main, name, {})
    for name in (
        "check_print_start_plate",
        "notify_missing_spool_assignments_on_print_start",
        "_store_start_tracking",
        "_record_energy_start",
        "_capture_timelapse_baseline_at_start",
        "_send_print_start_notification",
    ):
        monkeypatch.setattr(main, name, AsyncMock())
    monkeypatch.setattr(main.print_provenance, "capture_print_start", AsyncMock(return_value=False))
    monkeypatch.setattr(main, "_load_objects_from_archive", lambda *args: None)
    monkeypatch.setattr(main, "_maybe_start_layer_timelapse", lambda *args: False)
    monkeypatch.setattr(main, "spawn_background_task", lambda coro, **kwargs: coro.close())
    for name in ("get_status", "get_client", "get_current_print_user"):
        monkeypatch.setattr(main.printer_manager, name, lambda *args: None)
    monkeypatch.setattr(main.printer_manager, "get_printer", lambda *args: None)
    for name in ("send_print_start", "send_archive_updated", "send_archive_created"):
        monkeypatch.setattr(main.ws_manager, name, AsyncMock())
    for name in ("on_print_start", "on_archive_created"):
        monkeypatch.setattr(main.mqtt_relay, name, AsyncMock())
    monkeypatch.setattr(main.smart_plug_manager, "on_print_start", AsyncMock())
    monkeypatch.setattr(main, "get_cached_3mf", lambda *args: None)
    monkeypatch.setattr(main, "get_ftp_retry_settings", AsyncMock(return_value=(False, 0, 0, 30)))
    monkeypatch.setattr(main, "download_file_async", AsyncMock(return_value=False))
    monkeypatch.setattr(bambu_ftp, "get_cached_3mf", lambda *args: None)
    monkeypatch.setattr(bambu_ftp, "get_ftp_retry_settings", AsyncMock(return_value=(False, 0, 0, 30)))
    monkeypatch.setattr(bambu_ftp, "download_file_async", AsyncMock(return_value=False))
    monkeypatch.setattr(bambu_ftp, "list_files_async", AsyncMock(return_value=[]))
    monkeypatch.setattr(fallback_archive_recovery, "try_recover_fallback_archive", AsyncMock(return_value=False))


async def test_reprint_clears_prior_run_reason_and_end_but_keeps_history(
    quiet_start, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    ended = datetime(2026, 11, 9, 12)
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="part.gcode.3mf",
        status="failed",
        completed_at=ended,
        failure_reason="Previous heater failure",
        good_quantity=0,
        reject_quantity=1,
        user_verdict="bad",
    )
    previous = PrintLogEntry(
        archive_id=archive.id,
        printer_id=printer.id,
        print_name="part",
        status="failed",
        completed_at=ended,
        failure_reason="Previous heater failure",
    )
    db_session.add(previous)
    await db_session.commit()
    main.register_expected_print(printer.id, archive.filename, archive.id)
    await main.on_print_start(printer.id, {"filename": archive.filename, "subtask_name": "part"})
    await db_session.refresh(archive)
    await db_session.refresh(previous)
    assert archive.status == "printing"
    assert archive.failure_reason is None and archive.completed_at is None
    assert archive.user_verdict is None and archive.reject_quantity is None
    assert previous.failure_reason == "Previous heater failure" and previous.completed_at == ended


@pytest.mark.parametrize(
    "previous_plate,current_plate,source_plates,old_file,kept",
    [
        (2, 1, (), "present", True),
        (None, None, (), "present", True),
        (2, 2, (), "present", False),
        (None, 2, (2,), "present", False),
        (None, 2, (1, 2), "present", True),
        (2, 2, (), "missing", False),
        (None, 2, (), "no_reference", False),
    ],
)
async def test_reprint_only_removes_a_recording_of_its_own_plate(
    previous_plate,
    current_plate,
    source_plates,
    old_file,
    kept,
    quiet_start,
    db_session,
    printer_factory,
    archive_factory,
    tmp_path,
):
    printer = await printer_factory()
    relative = "archives/part/video.mp4"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    if old_file == "present":
        path.write_bytes(b"previous recording")
    if source_plates:
        with zipfile.ZipFile(path.parent / "part.gcode.3mf", "w") as file:
            for plate in source_plates:
                file.writestr(f"Metadata/plate_{plate}.gcode", "G28")
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="part.gcode.3mf",
        file_path="archives/part/part.gcode.3mf",
        status="completed",
        timelapse_path=None if old_file == "no_reference" else relative,
        timelapse_plate_id=previous_plate,
        timelapse_baseline={"names": ["old.mp4"], "trusted": True},
    )
    main.register_expected_print(printer.id, archive.filename, archive.id, plate_id=current_plate)
    await main.on_print_start(printer.id, {"filename": archive.filename, "subtask_name": "part"})
    await db_session.refresh(archive)
    assert archive.status == "printing" and archive.timelapse_path is None
    assert archive.timelapse_plate_id is None and archive.timelapse_baseline is None
    assert path.exists() is kept


@pytest.mark.parametrize("auto_archive", [False, True])
@pytest.mark.parametrize("deleted", ["soft", "missing"])
async def test_deleted_expected_source_is_archived_anew_only_when_enabled(
    auto_archive, deleted, quiet_start, db_session, printer_factory, archive_factory
):
    printer = await printer_factory(auto_archive=auto_archive)
    filename = "part.gcode.3mf"
    original = None
    if deleted == "soft":
        original = await archive_factory(
            printer.id, with_run=False, filename=filename, status="completed", deleted_at=datetime(2026, 11, 9)
        )
    expected_id = original.id if original else 99999
    main.register_expected_print(printer.id, filename, expected_id, created_by_id=87)
    await main.on_print_start(printer.id, {"filename": filename, "subtask_name": "part"})
    db_session.expire_all()
    rows = (await db_session.execute(select(PrintArchive).where(PrintArchive.deleted_at.is_(None)))).scalars().all()
    assert len(rows) == int(auto_archive)
    if rows:
        assert rows[0].id != expected_id and rows[0].status == "printing"
        assert rows[0].filename == filename
    if original:
        retained = await db_session.get(PrintArchive, expected_id)
        assert retained.deleted_at is not None and retained.status == "completed"
    main._send_print_start_notification.assert_awaited_once()
    assert not main._expected_prints
    assert not main._expected_print_creators
    assert not main._expected_print_registered_at


@pytest.mark.parametrize(
    "dispatch,queue,split",
    [
        (None, None, True),
        ("new", None, False),
        ("unrelated", "same", True),
        (None, "same", False),
        (None, "other-printer", True),
        (None, "pending", True),
    ],
)
async def test_new_identity_needs_current_dispatch_or_this_printers_printing_queue(
    dispatch, queue, split, quiet_start, monkeypatch, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="part.gcode.3mf",
        print_name="part",
        status="printing",
        subtask_id="old",
        started_at=datetime(2026, 11, 10, 8),
    )
    other = await printer_factory()
    main._active_prints[(printer.id, "obsolete-alias")] = archive.id
    main._active_prints[(other.id, "keep-other-printer")] = archive.id
    if queue:
        db_session.add(
            PrintQueueItem(
                archive_id=archive.id,
                printer_id=other.id if queue == "other-printer" else printer.id,
                status="pending" if queue == "pending" else "printing",
                position=1,
            )
        )
        await db_session.commit()
    monkeypatch.setattr(
        main.printer_manager, "get_client", lambda _: SimpleNamespace(last_dispatch_subtask_id=dispatch)
    )
    await main.on_print_start(
        printer.id, {"filename": archive.filename, "subtask_name": "part", "raw_data": {"subtask_id": "new"}}
    )
    await db_session.refresh(archive)
    rows = (await db_session.execute(select(PrintArchive).where(PrintArchive.printer_id == printer.id))).scalars().all()
    assert len(rows) == (2 if split else 1)
    assert archive.status == ("cancelled" if split else "printing")
    assert archive.subtask_id == ("old" if split else "new")
    if split:
        assert archive.failure_reason == "noStatusUpdate"
        assert (printer.id, "obsolete-alias") not in main._active_prints
    assert main._active_prints[(other.id, "keep-other-printer")] == archive.id


@pytest.mark.parametrize("status", ["cancelled", "completed"])
async def test_terminal_archive_with_same_identity_is_not_reopened(
    status, quiet_start, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="part.gcode.3mf",
        print_name="part",
        status=status,
        subtask_id="same",
        failure_reason="Stale legacy report",
    )
    await main.on_print_start(
        printer.id, {"filename": archive.filename, "subtask_name": "part", "raw_data": {"subtask_id": "same"}}
    )
    await db_session.refresh(archive)
    rows = (await db_session.execute(select(PrintArchive).where(PrintArchive.printer_id == printer.id))).scalars().all()
    assert len(rows) == 2 and archive.status == status
    assert archive.failure_reason == "Stale legacy report"


async def test_same_live_identity_resumes_without_overwriting_start_time(
    quiet_start, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    started = datetime(2026, 11, 9, 8)
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="part.gcode.3mf",
        print_name="part",
        status="printing",
        subtask_id="same",
        started_at=started,
    )
    await main.on_print_start(
        printer.id, {"filename": archive.filename, "subtask_name": "part", "raw_data": {"subtask_id": "same"}}
    )
    await db_session.refresh(archive)
    rows = (await db_session.execute(select(PrintArchive).where(PrintArchive.printer_id == printer.id))).scalars().all()
    assert len(rows) == 1 and archive.started_at == started and archive.status == "printing"


@pytest.mark.parametrize("reported", ["part.gcode.3mf", "/cache/part.gcode.3mf", "file:///cache/part.gcode.3mf"])
async def test_touchscreen_full_filename_is_the_first_download_candidate(
    reported, quiet_start, db_session, printer_factory
):
    printer = await printer_factory()
    await main.on_print_start(printer.id, {"filename": reported, "subtask_name": "part.gcode.3mf"})
    assert main.download_file_async.await_args_list[0].args[2] == "/part.gcode.3mf"


async def test_touchscreen_full_filename_matches_the_existing_live_archive(
    quiet_start, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="part.gcode.3mf",
        print_name="Different internal title",
        status="printing",
        subtask_id=None,
    )
    await main.on_print_start(printer.id, {"filename": "/cache/part.gcode.3mf", "subtask_name": "part.gcode.3mf"})
    assert main._active_prints[(printer.id, archive.filename)] == archive.id
    main.download_file_async.assert_not_awaited()


async def test_a_model_title_ending_in_3mf_keeps_its_actual_file_suffix(quiet_start, db_session, printer_factory):
    printer = await printer_factory()
    await main.on_print_start(printer.id, {"filename": "part.3mf.gcode.3mf", "subtask_name": "part.3mf"})
    assert main.download_file_async.await_args_list[0].args[2] == "/part.3mf.gcode.3mf"


async def test_detected_start_is_not_delayed_by_the_file_search(quiet_start, monkeypatch, db_session, printer_factory):
    printer = await printer_factory()
    detected = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    clock = [detected]
    monkeypatch.setattr(main, "datetime", SimpleNamespace(now=lambda *args: clock[0]))

    async def delayed_settings():
        clock[0] += timedelta(minutes=5)
        return False, 0, 0, 30

    monkeypatch.setattr(main, "get_ftp_retry_settings", delayed_settings)
    await main.on_print_start(printer.id, {"filename": "Part.gcode.3mf", "subtask_name": "Part"})
    archive = await db_session.scalar(select(PrintArchive).where(PrintArchive.printer_id == printer.id))
    assert archive.started_at == detected.replace(tzinfo=None)
    assert clock[0] > detected


async def test_touchscreen_repeat_borrows_an_earlier_runs_file(
    quiet_start, monkeypatch, db_session, printer_factory, archive_factory, tmp_path
):
    from backend.app.services import archive as archive_module
    from backend.tests.unit.services.test_repeat_print_source import GCODE, source_file

    printer = await printer_factory()
    source_file(tmp_path / "old.3mf")
    original = await archive_factory(
        printer.id,
        with_run=False,
        filename="Original card filename.gcode.3mf",
        file_path="old.3mf",
        total_layers=300,
        extra_data={"_print_data": {"subtask_name": "Internal title", "filename": GCODE}},
    )
    monkeypatch.setattr(archive_module, "settings", main.app_settings)
    monkeypatch.setattr(main, "cache_3mf_download", lambda *args: None)
    await main.on_print_start(
        printer.id,
        {
            "filename": GCODE,
            "subtask_name": "Internal title",
            "raw_data": {"total_layer_num": 300},
        },
    )
    fresh = await db_session.scalar(select(PrintArchive).where(PrintArchive.id != original.id))
    assert fresh is not None and fresh.file_path
    assert fresh.filename == original.filename
    assert fresh.extra_data["_print_data"]["_3mf_from_archive"] == original.id
    assert fresh.plate_id == 3 and fresh.status == "printing"
    assert (tmp_path / "old.3mf").is_file()


@pytest.mark.parametrize("listed_failure", [False, True])
async def test_repeat_falls_back_after_copy_failure_but_never_borrows_for_a_listed_failed_transfer(
    listed_failure, quiet_start, monkeypatch, db_session, printer_factory, archive_factory, tmp_path
):
    from backend.app.services import repeat_print_source
    from backend.tests.unit.services.test_repeat_print_source import GCODE, source_file

    printer = await printer_factory()
    source_file(tmp_path / "old.3mf")
    original = await archive_factory(
        printer.id, with_run=False, filename="Original card filename.gcode.3mf", file_path="old.3mf"
    )
    finder = AsyncMock(return_value=original)
    monkeypatch.setattr(repeat_print_source, "archived_repeat_source", finder)
    monkeypatch.setattr(repeat_print_source, "copy_repeat_source", AsyncMock(side_effect=OSError("disk full")))
    if listed_failure:
        monkeypatch.setattr(
            bambu_ftp, "list_files_async", AsyncMock(return_value=[{"name": "Internal title.gcode.3mf"}])
        )
    await main.on_print_start(printer.id, {"filename": GCODE, "subtask_name": "Internal title"})
    fresh = await db_session.scalar(select(PrintArchive).where(PrintArchive.id != original.id))
    assert fresh is not None and fresh.file_path == "" and fresh.status == "printing"
    assert finder.await_count == (0 if listed_failure else 1)
    assert (tmp_path / "old.3mf").is_file()
