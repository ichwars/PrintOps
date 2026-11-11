"""Keep printer-wide file-transfer refusals from consuming queued work."""

import logging
import time

from sqlalchemy import select, update

from backend.app.core.websocket import ws_manager
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.bambu_ftp import FtpFailureKind
from backend.app.services.notification_service import notification_service

logger = logging.getLogger(__name__)
RETRY_TAIL = "PrintOps will retry automatically"


def hold_reason(label: str, kind: FtpFailureKind | None) -> str:
    if kind is FtpFailureKind.STORAGE:
        return f"{label} refused to store the file, check its SD card or USB drive. {RETRY_TAIL}"
    if kind is FtpFailureKind.AUTH:
        return f"{label} refused the file transfer, check its access code on the Printers page. {RETRY_TAIL}"
    if kind is FtpFailureKind.SESSIONS:
        return (
            f"{label} has no file-transfer sessions left (421 too many connections), "
            f"if this persists for a few minutes, restart the printer. {RETRY_TAIL}"
        )
    return f"{label} is not accepting files, {RETRY_TAIL}"


def asks_nothing_new(reason: str) -> bool:
    return all(part.strip().startswith("Busy:") or part.strip().endswith(RETRY_TAIL) for part in reason.split(" | "))


async def requeue_refused_upload(scheduler, db, item, printer, error_msg, toast_uid, kind, delay):
    refusals = scheduler._upload_refusals.get(printer.id, 0) + 1
    scheduler._upload_refusals[printer.id] = refusals
    scheduler._upload_refusal_kind[printer.id] = kind
    retry_delay = delay(refusals)
    scheduler._upload_backoff[printer.id] = time.monotonic() + retry_delay
    values = {"error_message": None}
    if item.target_model:
        values["printer_id"] = None
    result = await db.execute(
        update(PrintQueueItem)
        .where(
            PrintQueueItem.id == item.id,
            PrintQueueItem.status == "pending",
            PrintQueueItem.printer_id == printer.id,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    row = (
        await db.execute(select(PrintQueueItem.status, PrintQueueItem.printer_id).where(PrintQueueItem.id == item.id))
    ).one_or_none()
    expected_printer = None if item.target_model else printer.id
    waiting = result.rowcount and row is not None and row.status == "pending" and row.printer_id == expected_printer
    reason = hold_reason(printer.name or f"Printer {printer.id}", kind)
    logger.warning(
        "Queue item %s: upload refused (%s); retained, retrying printer %s in %ss",
        item.id,
        error_msg,
        printer.id,
        retry_delay,
    )
    if waiting and scheduler._upload_refusal_notified.get(printer.id) != reason:
        scheduler._upload_refusal_notified[printer.id] = reason
        try:
            await notification_service.on_queue_job_waiting(
                job_name=await scheduler._get_job_name(db, item),
                target_model=item.target_model or printer.model or "",
                waiting_reason=reason,
                printer_id=printer.id,
                db=db,
            )
        except Exception as exc:
            logger.debug("Waiting notification failed for item %s: %s", item.id, exc)
    try:
        await ws_manager.send_queue_item_failed(
            user_id=toast_uid, queue_item_id=item.id, printer_id=printer.id, reason="upload_failed"
        )
    except Exception:
        pass
