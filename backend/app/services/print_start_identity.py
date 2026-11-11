"""Decide whether a differently identified print can reuse an active archive."""

from sqlalchemy import select

from backend.app.models.print_queue import PrintQueueItem


async def different_run(db, archive, printer_id, observed_id, client):
    if not observed_id or not archive.subtask_id or archive.subtask_id == observed_id:
        return False
    raw = getattr(client, "last_dispatch_subtask_id", None)
    dispatched = str(raw).strip() if isinstance(raw, (str, int)) and not isinstance(raw, bool) else ""
    if dispatched and dispatched != "0":
        return dispatched != observed_id
    queued = await db.scalar(
        select(PrintQueueItem.id)
        .where(
            PrintQueueItem.archive_id == archive.id,
            PrintQueueItem.printer_id == printer_id,
            PrintQueueItem.status == "printing",
        )
        .limit(1)
    )
    return queued is None
