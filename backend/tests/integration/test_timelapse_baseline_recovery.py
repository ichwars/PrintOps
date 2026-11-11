"""Persisted baseline recovery stays on its run, including a reused archive."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.models.archive import PrintArchive
from backend.app.services import timelapse_baseline as baseline
from backend.app.services.timelapse_archive import scan_for_timelapse_with_retries

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("aware", [False, True])
@pytest.mark.parametrize("change", ["none", "reprint", "finished", "trusted"])
async def test_recovery_only_updates_its_unread_running_archive(
    aware, change, test_engine, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    started = datetime(2026, 11, 10, 10)
    archive = await archive_factory(
        printer.id,
        with_run=False,
        status="printing",
        started_at=started,
        timelapse_baseline={"names": [], "trusted": False},
    )
    if change == "reprint":
        archive.started_at = started + timedelta(hours=1)
    elif change == "finished":
        archive.status = "completed"
    elif change == "trusted":
        archive.timelapse_baseline = {"names": ["already-read.avi"], "trusted": True}
    await db_session.commit()
    previous = archive.timelapse_baseline
    await baseline.persist_recovery(
        archive.id,
        printer.id,
        started.replace(tzinfo=timezone.utc) if aware else started,
        {"recovered.avi"},
        async_sessionmaker(test_engine, expire_on_commit=False),
    )
    await db_session.refresh(archive)
    assert archive.timelapse_baseline == (
        {"names": ["recovered.avi"], "trusted": True} if change == "none" else previous
    )


async def test_unread_memory_and_persisted_baselines_never_attach_stale_video(
    test_engine, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, timelapse_baseline={"names": [], "trusted": False})
    read = AsyncMock(return_value=([{"name": "stale.avi"}], "/timelapse"))
    service = AsyncMock()
    session = async_sessionmaker(test_engine, expire_on_commit=False)

    def make_service(db):
        async def get_archive(archive_id):
            return await db.get(PrintArchive, archive_id)

        service.get_archive = get_archive
        return service

    await scan_for_timelapse_with_retries(
        archive.id,
        baseline.BaselineNames(),
        session_factory=session,
        archive_service_factory=make_service,
        list_videos=read,
        websocket_manager=AsyncMock(),
    )
    read.assert_not_awaited()
    service.attach_timelapse.assert_not_awaited()


async def test_trusted_persisted_snapshot_beats_unread_restart_memory(
    monkeypatch, test_engine, printer_factory, archive_factory
):
    from backend.app.services import bambu_ftp

    printer = await printer_factory()
    archive = await archive_factory(
        printer.id, with_run=False, timelapse_baseline={"names": ["old.avi"], "trusted": True}
    )
    read = AsyncMock(return_value=([{"name": "old.avi"}, {"name": "new.avi"}], "/timelapse"))
    download = AsyncMock(return_value=b"complete video")
    monkeypatch.setattr(bambu_ftp, "download_file_bytes_async", download)
    monkeypatch.setattr(baseline.asyncio, "sleep", AsyncMock())
    service = AsyncMock()
    session = async_sessionmaker(test_engine, expire_on_commit=False)

    def make_service(db):
        async def get_archive(archive_id):
            return await db.get(PrintArchive, archive_id)

        service.get_archive = get_archive
        return service

    await scan_for_timelapse_with_retries(
        archive.id,
        baseline.BaselineNames(),
        session_factory=session,
        archive_service_factory=make_service,
        list_videos=read,
        websocket_manager=AsyncMock(),
    )
    service.attach_timelapse.assert_awaited_once_with(
        archive.id,
        b"complete video",
        "new.avi",
        expected_started_at=None,
        replace=False,
    )
    assert download.await_args.args[2] == "/timelapse/new.avi"
