"""Owned timelapse files and conditional attachment to a specific print run."""

from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path

from sqlalchemy import select, union_all, update
from sqlalchemy.orm.attributes import set_committed_value

from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
from backend.app.services.print_run_media import later_run_of_plate, newest_run, run_of
from backend.app.utils.archive_paths import archive_dir
from backend.app.utils.local_time import to_naive_utc
from backend.app.utils.safe_path import PathTraversalError, safe_join_under

logger = logging.getLogger(__name__)
ANY_RUN = object()


async def reset_for_reprint(archive, plate_id, *, base_dir):
    """Detach the prior video and return it for removal if its plate is known."""
    previous = archive.timelapse_path
    same_plate = type(plate_id) is int and plate_id > 0 and archive.timelapse_plate_id == plate_id
    if previous and archive.timelapse_plate_id is None:
        from backend.app.services.archive import plate_indexes_in_3mf
        from backend.app.services.running_print_archive import local_archive_file

        source = local_archive_file(archive, base_dir)
        plates = await asyncio.to_thread(plate_indexes_in_3mf, source) if source is not None else []
        same_plate = len(plates) == 1 and (plate_id is None or plates[0] in (None, plate_id))
    archive.timelapse_baseline = None
    archive.timelapse_path = None
    archive.timelapse_plate_id = None
    return previous if same_plate else None


async def remove_reprint_video(db, archive, previous, *, settings, plate_id=None):
    paths = {previous} if previous else set()
    if plate_id is not None and archive.started_at is not None:
        filters = (
            PrintLogEntry.archive_id == archive.id,
            PrintLogEntry.plate_id == plate_id,
            PrintLogEntry.started_at < to_naive_utc(archive.started_at),
            PrintLogEntry.timelapse_path.is_not(None),
        )
        rows = await db.scalars(select(PrintLogEntry.timelapse_path).where(*filters))
        old_paths = set(rows)
        if old_paths:
            await db.execute(update(PrintLogEntry).where(*filters).values(timelapse_path=None))
            await db.commit()
            paths.update(old_paths)
    parent = archive_dir(archive, base_dir=settings.base_dir, archive_root=settings.archive_dir)
    for path in paths:
        await remove_unreferenced(db, path, settings=settings, parent=parent)


async def announce_timelapse(archive_id, *, attached):
    from backend.app.core.websocket import ws_manager

    try:
        await ws_manager.send_archive_updated({"id": archive_id, "timelapse_attached": attached})
    except Exception:
        logger.debug("Could not announce timelapse change for archive %s", archive_id, exc_info=True)


def write_unique(parent, filename, data):
    target = safe_join_under(parent, filename, http=False)
    for _ in range(10):
        try:
            stream = target.open("xb")
        except FileExistsError:
            target = safe_join_under(
                parent, f"{Path(filename).stem}_{secrets.token_hex(6)}{Path(filename).suffix}", http=False
            )
            continue
        try:
            with stream:
                stream.write(data)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
    raise FileExistsError("Could not allocate a unique timelapse filename")


async def remove_unreferenced(db, relative_path, *, settings, parent):
    if not isinstance(relative_path, str) or not relative_path:
        return
    try:
        path = safe_join_under(settings.base_dir, relative_path, http=False)
        if not path.is_relative_to(parent.resolve()):
            return
        referenced = await db.scalar(
            union_all(
                select(PrintArchive.id).where(PrintArchive.timelapse_path == relative_path),
                select(PrintLogEntry.id).where(PrintLogEntry.timelapse_path == relative_path),
            )
            .limit(1)
            .execution_options(**{INCLUDE_OPEN_RUNS: True})
        )
        if referenced is None:
            await asyncio.to_thread(path.unlink, missing_ok=True)
    except (PathTraversalError, OSError):
        logger.warning("Could not remove replaced timelapse %r", relative_path)


async def attach(*args, **kwargs):
    # Keep the caller's DB session alive until its local write/transaction has
    # settled. Cancelling an HTTP/background waiter must not delete a file
    # whose commit already succeeded or abandon an owned partial write.
    task = asyncio.create_task(_attach(*args, **kwargs))
    cancelled = None
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError as error:
            if task.cancelled():
                raise
            cancelled = error
        except Exception as error:
            if cancelled is not None:
                raise cancelled from error
            raise
    if cancelled is not None:
        raise cancelled
    return result


async def _attach(
    service,
    archive_id,
    data,
    filename,
    *,
    settings,
    converter,
    spawn,
    expected_started_at=ANY_RUN,
    replace=True,
    plate_id=None,
    run_id=None,
    printer_id=None,
):
    archive = await service.get_archive(archive_id)
    if archive is None or getattr(archive, "deleted_at", None) is not None:
        return False
    guarded = expected_started_at is not ANY_RUN
    if guarded:
        expected_started_at = to_naive_utc(expected_started_at)
    if (
        run_id is None
        and guarded
        and (to_naive_utc(archive.started_at) != expected_started_at or (archive.timelapse_path and not replace))
    ):
        return False
    parent = archive_dir(archive, base_dir=settings.base_dir, archive_root=settings.archive_dir)
    parent.mkdir(parents=True, exist_ok=True)
    try:
        target = await asyncio.to_thread(write_unique, parent, filename, data)
    except PathTraversalError:
        logger.warning("Refusing unsafe timelapse filename %r for archive %s", filename, archive_id)
        return False
    previous = archive.timelapse_path
    relative = str(target.relative_to(settings.base_dir))
    try:
        if run_id is not None:
            claimed, previous = await claim_run_file(
                service.db, archive_id, run_id, printer_id, expected_started_at, relative, replace
            )
            if not claimed:
                await asyncio.to_thread(target.unlink, missing_ok=True)
                return False
        elif guarded:
            claimed, previous = await claim_file(
                service, archive, expected_started_at, relative, previous, replace, plate_id
            )
            if not claimed:
                await asyncio.to_thread(target.unlink, missing_ok=True)
                return False
        else:
            archive.timelapse_path = relative
            archive.timelapse_plate_id = plate_id
        if run_id is None:
            newest = await newest_run(service.db, archive_id)
            if newest is not None and newest.status != RUN_OPEN and newest.started_at == archive.started_at:
                if newest.printer_id == archive.printer_id:
                    newest.timelapse_path = relative
        await service.db.commit()
    except BaseException:
        await asyncio.to_thread(target.unlink, missing_ok=True)
        raise
    await announce_timelapse(archive_id, attached=True)
    await remove_unreferenced(service.db, previous, settings=settings, parent=parent)
    if not filename.lower().endswith(".mp4"):
        spawn(converter(archive_id, target), name=f"timelapse-convert-{archive_id}")
    return True


async def claim_run_file(db, archive_id, run_id, printer_id, expected_start, relative, replace):
    archive = await db.get(PrintArchive, archive_id, populate_existing=True, with_for_update=True)
    if archive is None or archive.deleted_at is not None:
        return False, None
    run = await run_of(db, archive_id, run_id, printer_id=printer_id)
    if run is None or run.status == RUN_OPEN or (run.timelapse_path and not replace):
        return False, None
    if expected_start is not ANY_RUN and to_naive_utc(run.started_at) != expected_start:
        return False, None
    if await later_run_of_plate(db, run):
        return False, None
    previous = run.timelapse_path
    updated = await db.execute(
        update(PrintLogEntry)
        .where(PrintLogEntry.id == run_id, PrintLogEntry.timelapse_path == previous)
        .values(timelapse_path=relative)
    )
    if updated.rowcount != 1:
        return False, None
    newest = await newest_run(db, archive_id)
    if newest is not None and newest.id == run_id:
        archive.timelapse_path = relative
        archive.timelapse_plate_id = run.plate_id
    return True, previous


async def claim_file(service, archive, started_at, relative, previous, replace, plate_id):
    archive_id = archive.id
    for _ in range(2):
        result = await service.db.execute(
            update(PrintArchive)
            .where(
                PrintArchive.id == archive_id,
                PrintArchive.deleted_at.is_(None),
                PrintArchive.started_at == started_at,
                PrintArchive.timelapse_path == previous,
            )
            .values(timelapse_path=relative, timelapse_plate_id=plate_id)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 1:
            set_committed_value(archive, "timelapse_path", relative)
            set_committed_value(archive, "timelapse_plate_id", plate_id)
            return True, previous
        await service.db.rollback()
        if not replace:
            break
        # A printer video may arrive while the camera writes its output. The
        # camera still wins on the same run; another run or deletion never does.
        archive = await service.get_archive(archive_id)
        if archive is None or archive.deleted_at is not None or to_naive_utc(archive.started_at) != started_at:
            break
        previous = archive.timelapse_path
    return False, previous


def reserve_conversion_path(source):
    """Reserve an output without replacing another run's existing MP4."""
    return write_unique(source.parent, source.with_suffix(".mp4").name, b"")


async def commit_conversion(db, archive_id, source, output, *, settings):
    source_path = str(source.relative_to(settings.base_dir))
    output_path = str(output.relative_to(settings.base_dir))
    run_update = await db.execute(
        update(PrintLogEntry)
        .where(
            PrintLogEntry.archive_id == archive_id,
            PrintLogEntry.timelapse_path == source_path,
            select(PrintArchive.id).where(PrintArchive.id == archive_id, PrintArchive.deleted_at.is_(None)).exists(),
        )
        .values(timelapse_path=output_path)
    )
    result = await db.execute(
        update(PrintArchive)
        .where(
            PrintArchive.id == archive_id,
            PrintArchive.deleted_at.is_(None),
            PrintArchive.timelapse_path == source_path,
        )
        .values(timelapse_path=output_path)
    )
    await db.commit()
    if result.rowcount != 1 and not run_update.rowcount:
        await asyncio.to_thread(output.unlink, missing_ok=True)
        return False
    await announce_timelapse(archive_id, attached=True)
    await remove_unreferenced(db, source_path, settings=settings, parent=source.parent)
    return True
