"""Separate firmware jobs from dispatched files that happen to share their name."""

import logging
import time

from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.utils.print_jobs import _job_stem, ignore_internal_printer_job, is_internal_printer_job

logger = logging.getLogger(__name__)


def expected_print_keys(printer_id, filename, subtask_name):
    keys = []
    if subtask_name:
        keys.extend((printer_id, name) for name in (subtask_name, f"{subtask_name}.3mf", f"{subtask_name}.gcode.3mf"))
    if filename:
        filename = filename.rsplit("/", 1)[-1]
        base = filename.replace(".gcode", "").replace(".3mf", "")
        keys.extend((printer_id, name) for name in (filename, base, f"{base}.3mf"))
    return keys


async def ignore_internal_event(printer_id, data, phase, *, expected, registered_at, ttl, active, session_factory):
    filename, subtask = data.get("filename"), data.get("subtask_name")
    if not is_internal_printer_job(filename, subtask):
        return False
    # /usr is firmware-owned even when a queued user file shares its basename.
    if not (filename or "").strip().replace("\\", "/").casefold().startswith("/usr/"):
        keys = expected_print_keys(printer_id, filename, subtask)
        now = time.monotonic()
        if (phase != "start" and any(key in active for key in keys)) or any(
            key in expected and key in registered_at and now - registered_at[key] < ttl for key in keys
        ):
            return False
        try:
            async with session_factory() as db:
                names = (
                    (
                        await db.execute(
                            select(PrintArchive.filename)
                            .join(PrintQueueItem, PrintQueueItem.archive_id == PrintArchive.id)
                            .where(PrintQueueItem.printer_id == printer_id, PrintQueueItem.status == "printing")
                        )
                    )
                    .scalars()
                    .all()
                )
            observed = {_job_stem(value) for value in (filename, subtask) if value}
            if any(isinstance(name, str) and _job_stem(name) in observed for name in names):
                return False
        except Exception as error:
            logger.warning("Could not check dispatch identity for printer %s: %s", printer_id, error)
    return ignore_internal_printer_job(data, logger, phase)
