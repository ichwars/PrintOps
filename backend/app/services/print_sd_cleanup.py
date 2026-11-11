"""Bound end-of-print SD cleanup so queue completion can proceed."""

import asyncio
from pathlib import PurePosixPath

from sqlalchemy import select

SD_CLEANUP_BUDGET_SECONDS = 45


def sd_files_in_use(state) -> set[str]:
    def text(value):
        return value.strip() if isinstance(value, str) else ""

    if state is None or text(getattr(state, "state", None)).upper() in {"", "UNKNOWN", "IDLE", "FINISH", "FAILED"}:
        return set()
    names = set()
    gcode_file = text(getattr(state, "gcode_file", None))
    if gcode_file:
        # Retain legal # characters rather than parsing them as URL fragments.
        names.add(PurePosixPath(gcode_file.split("://", 1)[-1]).name.lower())
    subtask = text(getattr(state, "subtask_name", None))
    if subtask:
        from backend.app.utils.filename import derive_remote_filename

        for name in (subtask, subtask.replace(" ", "_")):
            names.add(PurePosixPath(name).name.lower())
            names.add(PurePosixPath(derive_remote_filename(name)).name.lower())
            names.update(f"{name}{extension}".lower() for extension in (".3mf", ".gcode"))
    return names


async def cleanup_after_print(printer_id, subtask_name, archive_id, logger, session_factory, *, get_status=None):
    try:
        await asyncio.wait_for(
            _cleanup_after_print(printer_id, subtask_name, archive_id, logger, session_factory, get_status=get_status),
            timeout=SD_CLEANUP_BUDGET_SECONDS,
        )
    except TimeoutError:
        logger.warning(
            "SD cleanup on printer %s exceeded %ss; closing the print", printer_id, SD_CLEANUP_BUDGET_SECONDS
        )


async def _cleanup_after_print(printer_id, subtask_name, archive_id, logger, session_factory, *, get_status=None):
    # Cleanup: delete uploaded file from printer SD card to prevent phantom prints (Issue #374, #1542)
    # The print scheduler uploads files to the SD card root (/). Some printers (e.g. P1S, A1)
    # auto-start files found in root on power cycle, causing ghost prints.
    # Must run before the archive_id early-return so it executes even when archiving is disabled.
    if get_status is None:
        from backend.app.services.printer_manager import printer_manager

        get_status = printer_manager.get_status
    try:
        if subtask_name:
            archive_filename: str | None = None
            async with session_factory() as db:
                from backend.app.models.archive import PrintArchive
                from backend.app.models.printer import Printer

                result = await db.execute(select(Printer).where(Printer.id == printer_id))
                printer = result.scalar_one_or_none()
                if archive_id:
                    archive_row = await db.execute(select(PrintArchive.filename).where(PrintArchive.id == archive_id))
                    archive_filename = archive_row.scalar_one_or_none()

            if printer:
                from backend.app.services.bambu_ftp import DeleteResult, delete_file_async
                from backend.app.utils.filename import derive_remote_filename

                # Primary candidate: the exact path the dispatcher uploaded to
                # (derived from archive.filename via the same rule as upload).
                # Without it, a library row that ended up with a doubled
                # .gcode.3mf (#1542) leaves the real file behind because the
                # subtask_name + ext fallbacks below don't match what's on the
                # SD card. Fallbacks remain for archive-less prints (subtask
                # never resolved to an archive) and for older naming variants.
                candidate_paths: list[str] = []
                if archive_filename:
                    candidate_paths.append(f"/{derive_remote_filename(archive_filename)}")
                for ext in (".3mf", ".gcode"):
                    fallback = f"/{subtask_name}{ext}"
                    if fallback not in candidate_paths:
                        candidate_paths.append(fallback)

                # Three outcomes track across all candidates so the final log
                # line reflects what actually happened. The A1 in #1721 always
                # ends here with ``any_not_found=True`` and the others False
                # — its firmware auto-cleans the SD card before our cleanup
                # runs, every candidate FTP-DELE returns 550, and the old
                # code burned 3 retries × 2 s × 3 candidates per print
                # logging a misleading "may linger" WARNING on a successful
                # print.
                any_deleted = False
                any_real_failure = False
                any_not_found = False

                for remote_path in candidate_paths:
                    # Retry only the FAILED case — 550 NOT_FOUND will never
                    # recover by waiting, so a "file isn't here" answer
                    # advances immediately to the next candidate without
                    # consuming the retry budget.
                    for attempt in range(1, 4):
                        if PurePosixPath(remote_path).name.lower() in sd_files_in_use(get_status(printer_id)):
                            logger.info("SD cleanup keeps %s on %s: the printer is using it", remote_path, printer.name)
                            break
                        try:
                            delete_result = await delete_file_async(
                                printer.ip_address,
                                printer.access_code,
                                remote_path,
                                printer_model=printer.model,
                            )
                        except Exception as e:
                            delete_result = DeleteResult.FAILED
                            logger.warning(
                                "SD card cleanup attempt %d/3 raised for %s: %s",
                                attempt,
                                remote_path,
                                e,
                            )

                        if delete_result == DeleteResult.DELETED:
                            any_deleted = True
                            logger.info("Deleted %s from printer %s SD card", remote_path, printer.name)
                            break
                        if delete_result == DeleteResult.NOT_FOUND:
                            any_not_found = True
                            break  # 550 will not recover; try next candidate
                        # FAILED: real error — retry with backoff, then give up
                        if attempt < 3:
                            await asyncio.sleep(2)
                        else:
                            any_real_failure = True
                            logger.warning(
                                "SD card cleanup failed after 3 attempts for %s "
                                "(network/auth/transient error — file may linger on SD card)",
                                remote_path,
                            )

                if not any_deleted and not any_real_failure and any_not_found:
                    # Every candidate said "not here." Either the printer
                    # firmware swept the SD card itself (common on A1) or the
                    # dispatcher's upload path doesn't match our candidate
                    # rule. Either way: nothing to clean up, no warning.
                    logger.debug(
                        "SD card cleanup: nothing to delete on %s — every candidate returned 550 "
                        "(printer likely self-cleaned)",
                        printer.name,
                    )
    except Exception as e:
        logger.warning("SD card file cleanup failed for printer %s: %s", printer_id, e)
