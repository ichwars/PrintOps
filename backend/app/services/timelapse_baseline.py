"""Read and recover a print's card snapshot without trusting transport failures."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import update

from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
from backend.app.models.printer import Printer
from backend.app.services.print_log_run import entry_of_run
from backend.app.services.print_run_media import run_of
from backend.app.services.timelapse_archive import baseline_state, read_baseline_state
from backend.app.utils.local_time import to_naive_utc

logger = logging.getLogger(__name__)
DIRECTORIES = ("/timelapse", "/timelapse/video", "/record", "/recording")
VIDEO_EXTENSIONS = (".mp4", ".avi")
REREAD_INTERVAL = 120.0
REREAD_MAX_INTERVAL = 1800.0
REREAD_FAILED_ROUNDS = 5
REREAD_MAX_ROUNDS = 720
ACTIVE_STATES = {"PREPARE", "SLICING", "RUNNING", "PAUSE"}


class BaselineNames(set):
    """Keep snapshot trust on the run's set, including after memory retirement."""

    trusted: bool = False


async def list_videos(printer):
    from backend.app.services.bambu_ftp import FileListingError, ftps_background_blocked, list_files_strict_async
    from backend.app.services.ftp_listing import listing_missing

    last_error = None
    for path in DIRECTORIES:
        if ftps_background_blocked(printer.ip_address):
            raise FileListingError("Background timelapse read paused while the printer file service recovers")
        try:
            files = await list_files_strict_async(
                printer.ip_address, printer.access_code, path, printer_model=printer.model
            )
        except Exception as error:
            if not listing_missing(error):
                last_error = error
            continue
        videos = [
            row
            for row in files
            if not row.get("is_directory") and row.get("name", "").lower().endswith(VIDEO_EXTENSIONS)
        ]
        if videos:
            return videos, path
    # An empty successful directory cannot vouch for a different unread one.
    if last_error is not None:
        raise last_error
    return [], None


async def capture(
    printer,
    printer_id,
    *,
    baselines,
    list_videos,
    get_status,
    session_factory,
    spawn,
    archive_id=None,
    db=None,
    skip_if_present=False,
    preserve_stored=False,
    run_id=None,
):
    if skip_if_present and printer_id in baselines:
        return
    names = BaselineNames()
    baselines[printer_id] = names
    archive = await db.get(PrintArchive, archive_id) if db is not None and archive_id is not None else None
    run = None
    if archive is not None and run_id is not None:
        run = await run_of(db, archive_id, run_id, printer_id=printer_id)
    elif archive is not None and archive.printer_id == printer_id:
        run = await entry_of_run(db, archive_id, printer_id, archive.started_at)
    source = run if run is not None else archive
    run_started_at = source.started_at if source is not None else None
    stored = read_baseline_state(source.timelapse_baseline) if source is not None else None
    if preserve_stored and stored is not None and stored[1]:
        names.update(stored[0])
        names.trusted = True
        return
    try:
        files, _ = await list_videos(printer)
        names.update(row["name"] for row in files if row.get("name"))
        names.trusted = True
    except Exception as error:
        logger.warning("[TIMELAPSE] Could not read print-start card for printer %s: %s", printer_id, error)
    if baselines.get(printer_id) is not names:
        return
    if source is not None:
        source.timelapse_baseline = baseline_state(names, trusted=names.trusted)
        if archive is not source and archive.printer_id == printer_id and archive.started_at == source.started_at:
            archive.timelapse_baseline = source.timelapse_baseline
        await db.commit()
    if not names.trusted:
        spawn(
            reread(
                printer_id,
                names,
                archive_id,
                run_started_at,
                baselines=baselines,
                list_videos=list_videos,
                get_status=get_status,
                session_factory=session_factory,
                run_id=run.id if run is not None else None,
            ),
            name=f"reread-timelapse-baseline-{printer_id}",
        )


def reread_state(printer_id, names, baselines, get_status):
    if baselines.get(printer_id) is not names or names.trusted:
        return False
    status = get_status(printer_id)
    if status is None or not status.connected:
        return None
    if status.state not in ACTIVE_STATES:
        return False
    return True if status.timelapse else None


async def reread(
    printer_id, names, archive_id, started_at, *, baselines, list_videos, get_status, session_factory, run_id=None
):
    interval, failed = REREAD_INTERVAL, 0
    for _ in range(REREAD_MAX_ROUNDS):
        await asyncio.sleep(interval)
        state = reread_state(printer_id, names, baselines, get_status)
        if state is False:
            return
        if state is None:
            continue
        try:
            async with session_factory() as db:
                printer = await db.get(Printer, printer_id)
            if printer is None:
                return
            files, _ = await list_videos(printer)
        except Exception as error:
            failed += 1
            if failed >= REREAD_FAILED_ROUNDS:
                logger.warning(
                    "[TIMELAPSE] Card for printer %s unread after %s rounds; stopping reread", printer_id, failed
                )
                return
            logger.debug("[TIMELAPSE] Card reread failed for printer %s: %s", printer_id, error)
            interval = min(interval * 2, REREAD_MAX_INTERVAL)
            continue
        state = reread_state(printer_id, names, baselines, get_status)
        if state is False:
            return
        if state is None:
            continue
        names.update(row["name"] for row in files if row.get("name"))
        names.trusted = True
        if archive_id is not None:
            await persist_recovery(archive_id, printer_id, started_at, names, session_factory, run_id=run_id)
        return


async def persist_recovery(archive_id, printer_id, started_at, names, session_factory, *, run_id=None):
    started_at = to_naive_utc(started_at)
    try:
        async with session_factory() as db:
            if run_id is not None:
                await db.execute(
                    update(PrintLogEntry)
                    .where(
                        PrintLogEntry.id == run_id,
                        PrintLogEntry.archive_id == archive_id,
                        PrintLogEntry.printer_id == printer_id,
                        PrintLogEntry.started_at == started_at,
                        PrintLogEntry.status == RUN_OPEN,
                        PrintLogEntry.timelapse_baseline["trusted"].as_boolean().is_not(True),
                    )
                    .values(timelapse_baseline=baseline_state(names, trusted=True))
                    .execution_options(**{INCLUDE_OPEN_RUNS: True})
                )
            archive = await db.get(PrintArchive, archive_id)
            if archive is None or to_naive_utc(archive.started_at) != started_at or archive.printer_id != printer_id:
                await db.commit()
                return
            previous = archive.timelapse_baseline
            stored = read_baseline_state(previous)
            if stored is not None and stored[1]:
                await db.commit()
                return
            await db.execute(
                update(PrintArchive)
                .where(
                    PrintArchive.id == archive_id,
                    PrintArchive.printer_id == printer_id,
                    PrintArchive.started_at == started_at,
                    PrintArchive.status == "printing",
                    PrintArchive.timelapse_baseline["trusted"].as_boolean().is_not(True),
                )
                .values(timelapse_baseline=baseline_state(names, trusted=True))
            )
            await db.commit()
    except Exception as error:
        logger.warning("[TIMELAPSE] Could not persist recovered baseline for archive %s: %s", archive_id, error)
