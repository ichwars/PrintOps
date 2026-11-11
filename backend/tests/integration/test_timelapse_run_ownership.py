"""Long downloads, writes and stitches cannot update a later print's video."""

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.models.archive import PrintArchive
from backend.app.services import archive as archive_module, archive_timelapse, bambu_ftp
from backend.app.services.archive import ArchiveService
from backend.app.services.print_event_tasks import complete_layer_timelapse
from backend.app.services.timelapse_archive import scan_for_timelapse_with_retries

pytestmark = pytest.mark.asyncio
STARTED = datetime(2026, 11, 10, 10)


@pytest.fixture
def video_settings(tmp_path, monkeypatch):
    settings = SimpleNamespace(base_dir=tmp_path, archive_dir=tmp_path / "archives")
    monkeypatch.setattr(archive_module, "settings", settings)
    return settings


async def test_new_video_keeps_the_other_plates_file_and_tracks_the_new_plate(
    monkeypatch, async_client, db_session, printer_factory, archive_factory, video_settings
):
    from backend.app.api.routes import archives

    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, started_at=STARTED, file_path="archives/owned/file.3mf")
    kept = video_settings.base_dir / "archives/owned/layer_timelapse.mp4"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(b"earlier plate")
    assert await ArchiveService(db_session).attach_timelapse(
        archive.id, b"new plate", "layer_timelapse.mp4", expected_started_at=STARTED, plate_id=2
    )
    await db_session.refresh(archive)
    attached = video_settings.base_dir / archive.timelapse_path
    assert attached != kept and attached.read_bytes() == b"new plate"
    assert archive.timelapse_plate_id == 2 and kept.read_bytes() == b"earlier plate"
    monkeypatch.setattr(archives, "settings", video_settings)
    response = await async_client.delete(f"/api/v1/archives/{archive.id}/timelapse")
    assert response.status_code == 200, response.text
    await db_session.refresh(archive)
    assert archive.timelapse_path is None and archive.timelapse_plate_id is None
    assert not attached.exists() and kept.read_bytes() == b"earlier plate"


async def test_new_run_during_download_keeps_its_video_unattached(
    monkeypatch, test_engine, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, started_at=STARTED)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    attach = AsyncMock()

    def service(db):
        actual = ArchiveService(db)
        actual.attach_timelapse = attach
        return actual

    async def downloaded(*args, **kwargs):
        async with factory() as db:
            await db.execute(
                update(PrintArchive)
                .where(PrintArchive.id == archive.id)
                .values(started_at=STARTED + timedelta(hours=1), status="printing")
            )
            await db.commit()
        return b"old run video"

    monkeypatch.setattr(bambu_ftp, "download_file_bytes_async", downloaded)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    await scan_for_timelapse_with_retries(
        archive.id,
        set(),
        session_factory=factory,
        archive_service_factory=service,
        list_videos=AsyncMock(return_value=([{"name": "old.avi"}], "/timelapse")),
        websocket_manager=AsyncMock(),
    )
    attach.assert_not_awaited()
    await db_session.refresh(archive)
    assert archive.started_at == STARTED + timedelta(hours=1)
    assert archive.timelapse_path is None


@pytest.mark.parametrize("change", ["reprint", "deleted", "other-video"])
async def test_new_run_during_disk_write_loses_the_conditional_attachment(
    change, monkeypatch, test_engine, db_session, printer_factory, archive_factory, video_settings
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, started_at=STARTED, file_path="archives/owned/file.3mf")
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    wrote, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    original = archive_timelapse.write_unique

    def delayed(*args):
        path = original(*args)
        loop.call_soon_threadsafe(wrote.set)
        release.wait(5)
        return path

    monkeypatch.setattr(archive_timelapse, "write_unique", delayed)
    async with factory() as db:
        task = asyncio.create_task(
            ArchiveService(db).attach_timelapse(
                archive.id, b"old run", "old.mp4", expected_started_at=STARTED, replace=False
            )
        )
        try:
            await asyncio.wait_for(wrote.wait(), 3)
            async with factory() as other:
                changed = (
                    {"started_at": STARTED + timedelta(hours=1)}
                    if change == "reprint"
                    else (
                        {"deleted_at": STARTED}
                        if change == "deleted"
                        else {"timelapse_path": "archives/owned/other.mp4"}
                    )
                )
                await other.execute(update(PrintArchive).where(PrintArchive.id == archive.id).values(**changed))
                await other.commit()
        finally:
            release.set()
        assert await task is False
    await db_session.refresh(archive)
    assert archive.timelapse_path == ("archives/owned/other.mp4" if change == "other-video" else None)
    assert not (video_settings.archive_dir / "owned" / "old.mp4").exists()


async def test_cancelled_waiter_settles_owned_file_and_commit_before_session_closes(
    monkeypatch, test_engine, db_session, printer_factory, archive_factory, video_settings
):
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id, with_run=False, started_at=STARTED, file_path="archives/cancel/file.3mf"
    )
    wrote, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    original = archive_timelapse.write_unique

    def delayed(*args):
        path = original(*args)
        loop.call_soon_threadsafe(wrote.set)
        release.wait(5)
        return path

    monkeypatch.setattr(archive_timelapse, "write_unique", delayed)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as db:
        task = asyncio.create_task(
            ArchiveService(db).attach_timelapse(
                archive.id, b"complete recording", "video.mp4", expected_started_at=STARTED
            )
        )
        try:
            await asyncio.wait_for(wrote.wait(), 3)
            task.cancel()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    await db_session.refresh(archive)
    assert archive.timelapse_path == "archives/cancel/video.mp4"
    assert (video_settings.archive_dir / "cancel" / "video.mp4").read_bytes() == b"complete recording"


@pytest.mark.parametrize("aware", [False, True])
@pytest.mark.parametrize("shared", [False, True])
async def test_camera_replaces_printer_video_without_deleting_another_archives_reference(
    aware, shared, monkeypatch, test_engine, db_session, printer_factory, archive_factory, video_settings
):
    printer = await printer_factory()
    previous = video_settings.archive_dir / "owned" / "printer.mp4"
    previous.parent.mkdir(parents=True)
    previous.write_bytes(b"printer video")
    relative = "archives/owned/printer.mp4"
    archive = await archive_factory(
        printer.id, with_run=False, started_at=STARTED, file_path="archives/owned/file.3mf", timelapse_path=relative
    )
    if shared:
        await archive_factory(printer.id, with_run=False, filename="other.3mf", timelapse_path=relative)
    announce = AsyncMock()
    monkeypatch.setattr(archive_timelapse, "announce_timelapse", announce)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as db:
        assert await ArchiveService(db).attach_timelapse(
            archive.id,
            b"camera video",
            "layer_timelapse.mp4",
            expected_started_at=STARTED.replace(tzinfo=timezone.utc) if aware else STARTED,
        )
    await db_session.refresh(archive)
    assert archive.timelapse_path == "archives/owned/layer_timelapse.mp4"
    assert previous.exists() is shared
    announce.assert_awaited_once_with(archive.id, attached=True)


async def test_stale_converter_cannot_replace_the_new_video(
    test_engine, db_session, printer_factory, archive_factory, video_settings
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, timelapse_path="archives/new.mp4")
    source = video_settings.base_dir / "old.avi"
    output = video_settings.base_dir / "converted.mp4"
    source.write_bytes(b"old input")
    output.write_bytes(b"converted")
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as db:
        assert not await archive_timelapse.commit_conversion(db, archive.id, source, output, settings=video_settings)
    await db_session.refresh(archive)
    assert archive.timelapse_path == "archives/new.mp4"
    assert not output.exists()
    assert source.read_bytes() == b"old input"


async def test_camera_wins_if_printer_video_arrives_during_its_write(
    monkeypatch, test_engine, db_session, printer_factory, archive_factory, video_settings
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, started_at=STARTED, file_path="archives/late/file.3mf")
    wrote, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    original = archive_timelapse.write_unique

    def delayed(*args):
        result = original(*args)
        loop.call_soon_threadsafe(wrote.set)
        release.wait(5)
        return result

    monkeypatch.setattr(archive_timelapse, "write_unique", delayed)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as db:
        task = asyncio.create_task(
            ArchiveService(db).attach_timelapse(
                archive.id, b"camera recording", "camera.mp4", expected_started_at=STARTED
            )
        )
        try:
            await asyncio.wait_for(wrote.wait(), 3)
            previous = video_settings.archive_dir / "late" / "printer.mp4"
            previous.write_bytes(b"printer recording")
            async with factory() as other:
                await other.execute(
                    update(PrintArchive)
                    .where(PrintArchive.id == archive.id)
                    .values(timelapse_path="archives/late/printer.mp4")
                )
                await other.commit()
        finally:
            release.set()
        assert await task
    await db_session.refresh(archive)
    assert archive.timelapse_path == "archives/late/camera.mp4"
    assert not previous.exists()


async def test_stitch_finishing_on_a_new_run_is_dropped_and_temporary_is_removed(
    monkeypatch, test_engine, db_session, printer_factory, archive_factory, video_settings
):
    from backend.app.services import layer_timelapse

    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, started_at=STARTED)
    temporary = video_settings.base_dir / "stitched.mp4"
    temporary.write_bytes(b"old camera recording")
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def stitched(_):
        async with factory() as db:
            await db.execute(
                update(PrintArchive)
                .where(PrintArchive.id == archive.id)
                .values(started_at=STARTED + timedelta(hours=1))
            )
            await db.commit()
        return temporary

    monkeypatch.setattr(layer_timelapse, "on_print_complete", stitched)
    await complete_layer_timelapse(
        printer.id,
        "completed",
        archive.id,
        archive_module.logger,
        async_session=factory,
        ArchiveService=ArchiveService,
        asyncio=asyncio,
    )
    await db_session.refresh(archive)
    assert archive.timelapse_path is None
    assert not temporary.exists()


@pytest.mark.parametrize("unread", [False, True])
async def test_manual_scan_never_automatically_claims_another_runs_video(
    unread, monkeypatch, db_session, printer_factory, archive_factory
):
    from backend.app.api.routes import archives

    printer = await printer_factory()
    archive = await archive_factory(
        printer.id,
        with_run=False,
        filename="1.3mf",
        started_at=None,
        timelapse_baseline={"names": [], "trusted": False} if unread else None,
    )
    await archive_factory(
        printer.id, with_run=False, filename="earlier.3mf", timelapse_path="archives/earlier/video_2026-11-10.mp4"
    )
    listing = [{"name": "video_2026-11-10.avi", "is_directory": False, "size": 100}]
    monkeypatch.setattr(bambu_ftp, "list_files_async", AsyncMock(return_value=listing))
    download = AsyncMock()
    monkeypatch.setattr(bambu_ftp, "download_file_bytes_async", download)
    from backend.app.core.auth import OwnershipAccess

    response = await archives.scan_timelapse(archive.id, db=db_session, access=OwnershipAccess(None, True))
    assert response["status"] == "not_found"
    assert response["available_files"][0]["name"] == "video_2026-11-10.avi"
    download.assert_not_awaited()


@pytest.mark.parametrize("shared", [False, True])
async def test_delete_announces_change_and_keeps_other_archives_file(
    shared, monkeypatch, async_client, db_session, printer_factory, archive_factory, video_settings
):
    from backend.app.api.routes import archives
    from backend.app.core.websocket import ws_manager

    monkeypatch.setattr(archives, "settings", video_settings)
    announce = AsyncMock()
    monkeypatch.setattr(ws_manager, "send_archive_updated", announce)
    printer = await printer_factory()
    path = video_settings.archive_dir / "owned" / "delete.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"existing video")
    archive = await archive_factory(
        printer.id, with_run=False, file_path="archives/owned/model.3mf", timelapse_path="archives/owned/delete.mp4"
    )
    if shared:
        await archive_factory(
            printer.id, with_run=False, filename="other.3mf", timelapse_path="archives/owned/delete.mp4"
        )
    response = await async_client.delete(f"/api/v1/archives/{archive.id}/timelapse")
    assert response.status_code == 200, response.text
    await db_session.refresh(archive)
    assert archive.timelapse_path is None
    assert path.exists() is shared
    announce.assert_awaited_once_with({"id": archive.id, "timelapse_attached": False})


@pytest.mark.asyncio
async def test_parallel_plates_keep_their_own_videos_and_photos(
    async_client, db_session, archive_factory, printer_factory, tmp_path, monkeypatch
):
    from backend.app.core.config import settings
    from backend.app.services.print_log import write_log_entry
    from backend.app.services.print_run_media import record_finish_photo

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archives")
    first, second = await printer_factory(), await printer_factory()
    first_start = datetime(2026, 11, 11, 11)
    second_start = first_start + timedelta(minutes=2)
    archive = await archive_factory(
        second.id, with_run=False, file_path="archives/shared/model.3mf", plate_id=2, started_at=second_start
    )
    earlier = await write_log_entry(
        db_session, archive_id=archive.id, printer_id=first.id, status="completed", plate_id=1, started_at=first_start
    )
    later = await write_log_entry(
        db_session, archive_id=archive.id, printer_id=second.id, status="completed", plate_id=2, started_at=second_start
    )
    await db_session.commit()
    service = ArchiveService(db_session)
    assert await service.attach_timelapse(
        archive.id, b"plate two", "printer-video.mp4", run_id=later.id, printer_id=second.id
    )
    assert await service.attach_timelapse(
        archive.id, b"plate one", "printer-video.mp4", run_id=earlier.id, printer_id=first.id
    )
    await db_session.refresh(archive)
    await db_session.refresh(earlier)
    await db_session.refresh(later)
    assert archive.timelapse_path == later.timelapse_path
    assert archive.timelapse_plate_id == 2
    assert earlier.timelapse_path != later.timelapse_path
    assert not await service.attach_timelapse(
        archive.id, b"wrong printer", "wrong.mp4", run_id=earlier.id, printer_id=second.id
    )
    photos_dir = (tmp_path / archive.file_path).parent / "photos"
    photos_dir.mkdir()
    for run, printer, photo in ((earlier, first, "first.jpg"), (later, second, "second.jpg")):
        (photos_dir / photo).write_bytes(photo.encode())
        assert await record_finish_photo(db_session, archive.id, photo, run_id=run.id, printer_id=printer.id)

    path = f"/api/v1/archives/{archive.id}"
    history = (await async_client.get(f"{path}/runs")).json()["items"]
    assert [(run["id"], run["photos"], run["has_timelapse"]) for run in history] == [
        (later.id, ["second.jpg"], True),
        (earlier.id, ["first.jpg"], True),
    ]
    for run, video, photo in ((earlier, b"plate one", "first.jpg"), (later, b"plate two", "second.jpg")):
        response = await async_client.get(f"{path}/timelapse", params={"run_id": run.id})
        assert response.status_code == 200 and response.content == video
        response = await async_client.get(f"{path}/photos/{photo}", params={"run_id": run.id})
        assert response.status_code == 200 and response.content == photo.encode()
    response = await async_client.get(f"{path}/photos/second.jpg", params={"run_id": earlier.id})
    assert response.status_code == 404


async def test_new_print_replaces_only_its_plates_recording(
    db_session, archive_factory, printer_factory, video_settings
):
    from backend.app.services.print_log import write_log_entry

    printer = await printer_factory()
    archive = await archive_factory(
        printer.id, with_run=False, file_path="archives/shared/model.3mf", plate_id=2, started_at=STARTED
    )
    service = ArchiveService(db_session)
    rows = []
    for index, plate in enumerate([2, 1]):
        start = STARTED + timedelta(hours=index)
        row = await write_log_entry(
            db_session,
            status="completed",
            archive_id=archive.id,
            printer_id=printer.id,
            plate_id=plate,
            started_at=start,
        )
        await db_session.commit()
        assert await service.attach_timelapse(archive.id, b"video", f"plate{plate}.mp4", run_id=row.id)
        rows.append(row)
    other, replaced = rows
    await db_session.refresh(other)
    await db_session.refresh(replaced)
    other_path = video_settings.base_dir / other.timelapse_path
    old_path = video_settings.base_dir / replaced.timelapse_path
    archive.started_at = STARTED + timedelta(hours=2)
    previous = await archive_timelapse.reset_for_reprint(archive, 1, base_dir=video_settings.base_dir)
    await db_session.commit()
    await archive_timelapse.remove_reprint_video(db_session, archive, previous, settings=video_settings, plate_id=1)
    await db_session.refresh(replaced)
    assert replaced.timelapse_path is None
    assert other_path.is_file()
    assert not old_path.exists()


async def test_late_frame_replaces_only_its_runs_existing_photo(
    db_session, archive_factory, printer_factory, video_settings
):
    from backend.app.services.print_log import write_log_entry
    from backend.app.services.print_run_media import record_finish_photo, replace_finish_photo

    printer = await printer_factory()
    archive = await archive_factory(
        printer.id, with_run=False, file_path="archives/shared/model.3mf", plate_id=1, started_at=STARTED
    )
    run = await write_log_entry(
        db_session, status="completed", archive_id=archive.id, printer_id=printer.id, started_at=STARTED
    )
    photos = video_settings.base_dir / "archives/shared/photos"
    photos.mkdir(parents=True)
    (photos / "live.jpg").write_bytes(b"live frame")
    (photos / "timelapse.jpg").write_bytes(b"timelapse frame")
    assert await record_finish_photo(db_session, archive.id, "live.jpg", run_id=run.id, printer_id=printer.id)
    assert not await replace_finish_photo(
        db_session, archive.id, run.id + 1, "live.jpg", "timelapse.jpg", settings=video_settings
    )
    assert (photos / "live.jpg").read_bytes() == b"live frame"
    assert await replace_finish_photo(
        db_session, archive.id, run.id, "live.jpg", "timelapse.jpg", settings=video_settings
    )
    assert archive.photos == run.photos == ["live.jpg"]
    assert (photos / "live.jpg").read_bytes() == b"timelapse frame"
    assert not (photos / "timelapse.jpg").exists()


async def test_printer_scan_uses_the_runs_printer_and_saved_baseline(
    db_session, test_engine, archive_factory, printer_factory, video_settings, monkeypatch
):
    from backend.app.services.print_log import write_log_entry
    from backend.app.services.timelapse_archive import baseline_state

    first, second = await printer_factory(), await printer_factory()
    archive = await archive_factory(
        second.id,
        with_run=False,
        file_path="archives/shared/model.3mf",
        plate_id=2,
        started_at=STARTED + timedelta(minutes=1),
    )
    run = await write_log_entry(
        db_session, status="completed", archive_id=archive.id, printer_id=first.id, plate_id=1, started_at=STARTED
    )
    run.timelapse_baseline = baseline_state({"before.mp4"}, trusted=True)
    await db_session.commit()

    async def list_files(printer):
        assert printer.id == first.id
        return [{"name": "before.mp4"}, {"name": "run-one.mp4"}], "/timelapse"

    download = AsyncMock(return_value=b"first printer video")
    monkeypatch.setattr(bambu_ftp, "download_file_bytes_async", download)
    monkeypatch.setattr("backend.app.services.timelapse_archive.asyncio.sleep", AsyncMock())
    await scan_for_timelapse_with_retries(
        archive.id,
        None,
        session_factory=async_sessionmaker(test_engine, expire_on_commit=False),
        archive_service_factory=ArchiveService,
        list_videos=list_files,
        websocket_manager=None,
        run_id=run.id,
    )
    await db_session.refresh(run)
    assert (video_settings.base_dir / run.timelapse_path).read_bytes() == b"first printer video"
    assert download.await_args.args[2] == "/timelapse/run-one.mp4"
