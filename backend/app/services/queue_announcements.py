"""Announce committed queue items to the MQTT relay and notification channels."""

import logging
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer

logger = logging.getLogger(__name__)


def _job_summary(rows) -> str:
    names = [
        filename.removesuffix(".gcode.3mf").removesuffix(".3mf")
        if (filename := row.archive_filename or row.library_filename)
        else f"Job #{row.id}"
        for row in rows
    ]
    distinct = list(dict.fromkeys(names))
    if len(distinct) == 1:
        return f"{distinct[0]} ×{len(names)}" if len(names) > 1 else distinct[0]
    listed = ", ".join(distinct[:3]) + (", …" if len(distinct) > 3 else "")
    return f"{len(names)} jobs ({listed})"


async def announce_queue_jobs_added(item_ids: Sequence[int], *, session_factory=None) -> None:
    """Send one user notification per target and one MQTT event per queue item."""
    if not item_ids:
        return
    from backend.app.core.database import async_session

    sessions = session_factory or async_session
    try:
        async with sessions() as db:
            await _announce(db, item_ids)
    except Exception:
        logger.warning("Could not announce new queue items", exc_info=True)


async def _announce(db, item_ids):
    from backend.app.services.mqtt_relay import mqtt_relay
    from backend.app.services.notification_service import notification_service

    rows = (
        await db.execute(
            select(
                PrintQueueItem.id,
                PrintQueueItem.printer_id,
                PrintQueueItem.target_model,
                Printer.name.label("printer_name"),
                PrintArchive.filename.label("archive_filename"),
                LibraryFile.filename.label("library_filename"),
            )
            .outerjoin(Printer, Printer.id == PrintQueueItem.printer_id)
            .outerjoin(PrintArchive, PrintArchive.id == PrintQueueItem.archive_id)
            .outerjoin(LibraryFile, LibraryFile.id == PrintQueueItem.library_file_id)
            .where(PrintQueueItem.id.in_(item_ids))
            .order_by(PrintQueueItem.position, PrintQueueItem.id)
        )
    ).all()

    groups = defaultdict(list)
    for row in rows:
        groups[row.printer_id].append(row)
        try:
            await mqtt_relay.on_queue_job_added(
                job_id=row.id,
                filename=row.archive_filename or row.library_filename or "",
                printer_id=row.printer_id,
                printer_name=row.printer_name,
            )
        except Exception:
            logger.debug("Could not publish MQTT queue event %s", row.id, exc_info=True)

    for printer_id, group in groups.items():
        printer_name = group[0].printer_name
        models = list(dict.fromkeys(row.target_model for row in group if row.target_model))
        target = printer_name or (f"Any {' / '.join(models)}" if models else "Unassigned")
        try:
            await notification_service.on_queue_job_added(
                _job_summary(group), target, db, printer_id=printer_id, printer_name=printer_name
            )
        except Exception:
            await db.rollback()
            logger.warning("Could not send queue notification for printer %s", printer_id, exc_info=True)
