"""Race-safe association of printer timelapse files with print archives."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy import or_, select

from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, PrintLogEntry
from backend.app.models.printer import Printer
from backend.app.services.print_run_media import later_print_on_printer, later_run_of_plate, run_of

logger = logging.getLogger(__name__)
_scan_locks: dict[int, asyncio.Lock] = {}


def baseline_state(names: set[str], *, trusted: bool) -> dict:
    """Build the JSON-safe persisted baseline representation."""
    return {"names": sorted(name for name in names if name), "trusted": trusted}


def read_baseline_state(value: object) -> tuple[set[str], bool] | None:
    if not isinstance(value, dict) or not isinstance(value.get("names"), list):
        return None
    names = {name for name in value["names"] if isinstance(name, str) and name}
    return names, value.get("trusted") is True


async def _claimed_names(db, printer_id: int, archive_id: int, run_id: int | None = None) -> set[str]:
    result = await db.execute(
        select(PrintArchive.timelapse_path).where(
            PrintArchive.printer_id == printer_id,
            PrintArchive.id != archive_id,
            PrintArchive.timelapse_path.isnot(None),
        )
    )
    names = {Path(path).stem for path in result.scalars().all() if isinstance(path, str) and path}
    runs = select(PrintLogEntry.timelapse_path).where(
        PrintLogEntry.printer_id == printer_id,
        PrintLogEntry.timelapse_path.is_not(None),
    )
    if run_id is not None:
        runs = runs.where(PrintLogEntry.id != run_id)
    else:
        runs = runs.where(or_(PrintLogEntry.archive_id.is_(None), PrintLogEntry.archive_id != archive_id))
    paths = await db.scalars(runs.execution_options(**{INCLUDE_OPEN_RUNS: True}))
    names.update(Path(path).stem for path in paths if path)
    return names


async def _scan_source(service, archive_id, run_id):
    archive = await service.get_archive(archive_id)
    if archive is None or getattr(archive, "deleted_at", None) is not None or run_id is None:
        return archive if archive is not None and getattr(archive, "deleted_at", None) is None else None
    run = await run_of(service.db, archive_id, run_id)
    if run is None or run.started_at is None:
        return None
    if await later_print_on_printer(service.db, run) or await later_run_of_plate(service.db, run):
        return None
    return run


async def scan_for_timelapse_with_retries(
    archive_id: int,
    baseline_names: set[str] | None,
    *,
    session_factory,
    archive_service_factory,
    list_videos: Callable[[Printer], Awaitable[tuple[list[dict], str | None]]],
    websocket_manager,
    plate_id: int | None = None,
    run_id: int | None = None,
) -> None:
    """Attach only one unambiguous, unclaimed video created after baseline."""
    from backend.app.services.bambu_ftp import download_file_bytes_async

    async with session_factory() as db:
        service = archive_service_factory(db)
        archive = await _scan_source(service, archive_id, run_id)
        if archive is None:
            logger.warning("[TIMELAPSE] Archive %s not found, aborting", archive_id)
            return
        if archive.timelapse_path:
            logger.info("[TIMELAPSE] Archive %s already has timelapse attached", archive_id)
            return
        if not archive.printer_id:
            logger.warning("[TIMELAPSE] Archive %s has no printer, aborting", archive_id)
            return

        printer_id = archive.printer_id
        run_started_at = archive.started_at
        lock = _scan_locks.setdefault(printer_id, asyncio.Lock())

    async with lock:
        async with session_factory() as db:
            service = archive_service_factory(db)
            archive = await _scan_source(service, archive_id, run_id)
            if (
                archive is None
                or archive.timelapse_path
                or archive.started_at != run_started_at
                or archive.printer_id != printer_id
            ):
                return
            printer = (await db.execute(select(Printer).where(Printer.id == archive.printer_id))).scalar_one_or_none()
            if printer is None:
                logger.warning("[TIMELAPSE] Printer not found for archive %s", archive_id)
                return

            persisted = read_baseline_state(getattr(archive, "timelapse_baseline", None))
            if persisted is not None and (baseline_names is None or persisted[1]):
                baseline, trusted = persisted
            elif baseline_names is not None:
                baseline = set(baseline_names)
                trusted = getattr(baseline_names, "trusted", True)
            elif run_id is not None:
                baseline, trusted = set(), False
            else:
                try:
                    files, _ = await list_videos(printer)
                    baseline = {row.get("name", "") for row in files if row.get("name")}
                    trusted = True
                except Exception as exc:
                    logger.warning("[TIMELAPSE] Completion baseline failed for archive %s: %s", archive_id, exc)
                    baseline, trusted = set(), False

            if not trusted:
                logger.warning(
                    "[TIMELAPSE] Baseline for archive %s is untrusted; refusing automatic association",
                    archive_id,
                )
                return

        retry_delays = [5, 10, 20, 30]
        for attempt, delay in enumerate(retry_delays, 1):
            logger.info(
                "[TIMELAPSE] Attempt %s/%s: waiting %ss for archive %s",
                attempt,
                len(retry_delays),
                delay,
                archive_id,
            )
            await asyncio.sleep(delay)
            try:
                async with session_factory() as db:
                    service = archive_service_factory(db)
                    archive = await _scan_source(service, archive_id, run_id)
                    if (
                        archive is None
                        or archive.timelapse_path
                        or archive.started_at != run_started_at
                        or archive.printer_id != printer_id
                    ):
                        return
                    printer = (
                        await db.execute(select(Printer).where(Printer.id == archive.printer_id))
                    ).scalar_one_or_none()
                    if printer is None:
                        return

                    videos, found_path = await list_videos(printer)
                    claimed = await _claimed_names(db, printer_id, archive_id, run_id)
                    candidates = [
                        row
                        for row in videos
                        if row.get("name") and row["name"] not in baseline and Path(row["name"]).stem not in claimed
                    ]
                    if len(candidates) != 1:
                        if len(candidates) > 1:
                            logger.warning(
                                "[TIMELAPSE] Archive %s has ambiguous new videos in %s: %s",
                                archive_id,
                                found_path,
                                [row.get("name") for row in candidates],
                            )
                        continue

                    target = candidates[0]
                    file_name = target["name"]
                    remote_path = target.get("path") or f"/timelapse/{file_name}"
                    await db.close()
                    data = await download_file_bytes_async(
                        printer.ip_address,
                        printer.access_code,
                        remote_path,
                        printer_model=printer.model,
                        total_bytes=target.get("size") or 0,
                    )
                    current = await _scan_source(service, archive_id, run_id)
                    if current is None or current.timelapse_path or current.started_at != run_started_at:
                        return
                    if data and await service.attach_timelapse(
                        archive_id,
                        data,
                        file_name,
                        expected_started_at=run_started_at,
                        replace=False,
                        **({"plate_id": plate_id} if plate_id is not None else {}),
                        **({"run_id": run_id, "printer_id": printer_id} if run_id is not None else {}),
                    ):
                        logger.info("[TIMELAPSE] Attached %s to archive %s", file_name, archive_id)
                        return
            except Exception as exc:
                logger.warning("[TIMELAPSE] Attempt %s failed for archive %s: %s", attempt, archive_id, exc)

        logger.warning("[TIMELAPSE] All attempts exhausted for archive %s", archive_id)
