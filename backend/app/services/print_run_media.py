"""Resolve media by the print that actually produced it."""

import asyncio
from pathlib import Path

from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
from backend.app.utils.archive_paths import archive_dir
from backend.app.utils.safe_path import assert_under, safe_join_under


async def run_of(db, archive_id, run_id, *, printer_id=None):
    query = select(PrintLogEntry).where(PrintLogEntry.id == run_id, PrintLogEntry.archive_id == archive_id)
    if printer_id is not None:
        query = query.where(PrintLogEntry.printer_id == printer_id)
    return await db.scalar(query.execution_options(populate_existing=True, **{INCLUDE_OPEN_RUNS: True}))


async def newest_run(db, archive_id):
    return await db.scalar(
        select(PrintLogEntry)
        .where(PrintLogEntry.archive_id == archive_id)
        .order_by(PrintLogEntry.started_at.desc().nulls_last(), PrintLogEntry.id.desc())
        .limit(1)
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )


async def record_finish_photo(db, archive_id, filename, *, run_id=None, printer_id=None):
    """Write both the exact run's photo and the archive gallery reference."""
    archive = await db.get(PrintArchive, archive_id, populate_existing=True, with_for_update=True)
    if archive is None or archive.deleted_at is not None:
        return False
    if run_id is not None:
        run = await run_of(db, archive_id, run_id, printer_id=printer_id)
        if run is None or run.status == RUN_OPEN:
            return False
        run.photos = list(dict.fromkeys([*(run.photos or []), filename]))
    archive.photos = list(dict.fromkeys([*(archive.photos or []), filename]))
    await db.commit()
    return True


def media_directory(archive, settings) -> Path:
    return assert_under(
        settings.base_dir,
        archive_dir(archive, base_dir=settings.base_dir, archive_root=settings.archive_dir),
    )


async def later_print_on_printer(db, run):
    if run is None or run.started_at is None:
        return False
    return (
        await db.scalar(
            select(PrintLogEntry.id)
            .where(PrintLogEntry.printer_id == run.printer_id, PrintLogEntry.started_at > run.started_at)
            .limit(1)
            .execution_options(**{INCLUDE_OPEN_RUNS: True})
        )
        is not None
    )


async def later_run_of_plate(db, run):
    if run.plate_id is None or run.started_at is None:
        return False
    return (
        await db.scalar(
            select(PrintLogEntry.id)
            .where(
                PrintLogEntry.archive_id == run.archive_id,
                PrintLogEntry.plate_id == run.plate_id,
                PrintLogEntry.started_at > run.started_at,
            )
            .limit(1)
            .execution_options(**{INCLUDE_OPEN_RUNS: True})
        )
        is not None
    )


async def replace_finish_photo(db, archive_id, run_id, old_photo, new_photo, *, settings):
    archive = await db.get(PrintArchive, archive_id, populate_existing=True, with_for_update=True)
    if archive is None or archive.deleted_at is not None or old_photo not in (archive.photos or []):
        return False
    run = await run_of(db, archive_id, run_id)
    if run is None or old_photo not in (run.photos or []):
        return False
    photos = safe_join_under(media_directory(archive, settings), "photos", http=False)
    previous = safe_join_under(photos, old_photo, http=False)
    if not previous.is_file():
        return False
    replacement = safe_join_under(photos, new_photo, http=False)
    await asyncio.to_thread(replacement.replace, previous)
    return True
