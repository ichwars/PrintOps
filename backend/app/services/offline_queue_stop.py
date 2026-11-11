"""Record an offline stop without pretending its consumption is known."""

from datetime import datetime, timezone

from sqlalchemy import select, update

from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.services.print_log import write_log_entry
from backend.app.services.print_log_run import open_print_runs, project_latest_finished_run


async def record_offline_stop(db, item):
    archive = await db.get(PrintArchive, item.archive_id, with_for_update=True) if item.archive_id else None
    if archive is None or archive.deleted_at is not None:
        return None, None
    run = await db.scalar(
        open_print_runs(item.printer_id).where(
            PrintLogEntry.archive_id == archive.id, PrintLogEntry.queue_item_id == item.id
        )
    )
    if run is None and archive.status != "printing":
        return None, None
    started_at = run.started_at if run is not None else archive.started_at
    other = await db.scalar(
        select(PrintQueueItem.id)
        .where(
            PrintQueueItem.archive_id == archive.id,
            PrintQueueItem.status == "printing",
            PrintQueueItem.printer_id != item.printer_id,
        )
        .limit(1)
    )
    archive_status = None
    ended = datetime.now(timezone.utc)
    if run is None and other is None and archive.printer_id == item.printer_id and archive.started_at == started_at:
        changed = await db.execute(
            update(PrintArchive)
            .where(
                PrintArchive.id == archive.id,
                PrintArchive.status == "printing",
                PrintArchive.deleted_at.is_(None),
                PrintArchive.started_at == archive.started_at,
                PrintArchive.printer_id == item.printer_id,
                ~select(PrintQueueItem.id)
                .where(
                    PrintQueueItem.archive_id == archive.id,
                    PrintQueueItem.status == "printing",
                    PrintQueueItem.printer_id != item.printer_id,
                )
                .exists(),
            )
            .values(status="cancelled", completed_at=ended, failure_reason="userCancelled")
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            return None, None
        archive_status = "cancelled"
    completed = await write_log_entry(
        db,
        run_id=run.id if run is not None else None,
        archive_id=archive.id,
        queue_item_id=item.id,
        printer_id=item.printer_id,
        printer_name=await db.scalar(select(Printer.name).where(Printer.id == item.printer_id)),
        print_name=archive.print_name,
        status="cancelled",
        started_at=started_at,
        plate_id=run.plate_id if run is not None else item.plate_id,
        completed_at=ended,
        failure_reason="userCancelled",
        filament_type=archive.filament_type,
        filament_color=archive.filament_color,
        thumbnail_path=archive.thumbnail_path,
        created_by_id=archive.created_by_id,
        reconciled=True,
        duration_unmeasured=True,
        ended_offline=True,
    )
    if run is not None:
        archive_status = await project_latest_finished_run(db, archive)
    return completed, archive_status
