"""Race-safe association of printer timelapse files with print archives."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.models.printer import Printer

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


async def _claimed_names(db, printer_id: int, archive_id: int) -> set[str]:
    result = await db.execute(
        select(PrintArchive.timelapse_path).where(
            PrintArchive.printer_id == printer_id,
            PrintArchive.id != archive_id,
            PrintArchive.timelapse_path.isnot(None),
        )
    )
    return {Path(path).name for path in result.scalars().all() if isinstance(path, str) and path}


async def scan_for_timelapse_with_retries(
    archive_id: int,
    baseline_names: set[str] | None,
    *,
    session_factory,
    archive_service_factory,
    list_videos: Callable[[Printer], Awaitable[tuple[list[dict], str | None]]],
    websocket_manager,
) -> None:
    """Attach only one unambiguous, unclaimed video created after baseline."""
    from backend.app.services.bambu_ftp import download_file_bytes_async

    async with session_factory() as db:
        service = archive_service_factory(db)
        archive = await service.get_archive(archive_id)
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
        lock = _scan_locks.setdefault(printer_id, asyncio.Lock())

    async with lock:
        async with session_factory() as db:
            service = archive_service_factory(db)
            archive = await service.get_archive(archive_id)
            if archive is None or archive.timelapse_path:
                return
            printer = (await db.execute(select(Printer).where(Printer.id == archive.printer_id))).scalar_one_or_none()
            if printer is None:
                logger.warning("[TIMELAPSE] Printer not found for archive %s", archive_id)
                return

            if baseline_names is not None:
                baseline = set(baseline_names)
                trusted = True
            else:
                persisted = read_baseline_state(getattr(archive, "timelapse_baseline", None))
                if persisted is not None:
                    baseline, trusted = persisted
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
                    archive = await service.get_archive(archive_id)
                    if archive is None or archive.timelapse_path:
                        return
                    printer = (
                        await db.execute(select(Printer).where(Printer.id == archive.printer_id))
                    ).scalar_one_or_none()
                    if printer is None:
                        return

                    videos, found_path = await list_videos(printer)
                    claimed = await _claimed_names(db, archive.printer_id, archive_id)
                    candidates = [
                        row
                        for row in videos
                        if row.get("name") and row["name"] not in baseline and row["name"] not in claimed
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
                    data = await download_file_bytes_async(
                        printer.ip_address,
                        printer.access_code,
                        remote_path,
                        printer_model=printer.model,
                    )
                    if data and await service.attach_timelapse(archive_id, data, file_name):
                        await websocket_manager.send_archive_updated({"id": archive_id, "timelapse_attached": True})
                        logger.info("[TIMELAPSE] Attached %s to archive %s", file_name, archive_id)
                        return
            except Exception as exc:
                logger.warning("[TIMELAPSE] Attempt %s failed for archive %s: %s", attempt, archive_id, exc)

        logger.warning("[TIMELAPSE] All attempts exhausted for archive %s", archive_id)
