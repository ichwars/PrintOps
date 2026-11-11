import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import check_permission, check_printer_access, get_api_key, is_auth_enabled
from backend.app.core.config import settings
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import (
    RowVisibility,
    require_archive_source,
    require_queue_creation,
    resolve_row_visibility,
)
from backend.app.models.api_key import APIKey
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.schemas.printer import HMSErrorResponse, hms_error_responses
from backend.app.services.print_control import STOPPABLE_STATES, stop_print_by_user
from backend.app.services.print_defaults import default_print_options
from backend.app.services.printer_manager import printer_manager
from backend.app.services.queue_announcements import announce_queue_jobs_added
from backend.app.services.queue_position import next_queue_position
from backend.app.services.queue_source_metadata import printed_plate_of_multi_plate_file, saved_slicer_ams_mapping
from backend.app.utils.local_time import to_naive_utc
from backend.app.utils.safe_path import safe_join_under

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


# Request schemas
class QueueAddRequest(BaseModel):
    archive_id: int
    printer_id: int
    project_id: int | None = None
    scheduled_time: str | None = None  # ISO format datetime
    require_previous_success: bool = False
    auto_off_after: bool = False


class QueueAddResponse(BaseModel):
    id: int
    archive_id: int
    printer_id: int
    position: int
    status: str
    message: str


class PrinterStatusResponse(BaseModel):
    id: int
    name: str
    serial_number: str
    connected: bool
    state: str | None
    current_print: str | None
    progress: float | None
    remaining_time: int | None
    remaining_seconds: int | None = None
    layer_num: int | None = None
    total_layers: int | None = None
    subtask_id: str | None = None
    hms_errors: list[HMSErrorResponse] = []


class QueueStatusResponse(BaseModel):
    printer_id: int
    printer_name: str
    pending: int
    printing: int
    items: list[dict]


def _job_id(subtask_id) -> str | None:
    if subtask_id is None:
        return None
    value = str(subtask_id).strip()
    return None if value in ("", "0") else value


async def _webhook_visibility(db: AsyncSession, api_key: APIKey) -> RowVisibility:
    if not await is_auth_enabled(db):
        return RowVisibility(None, None, True)
    visibility = await resolve_row_visibility(db, None, api_key)
    if api_key.user_id is not None and visibility.user is None:
        raise HTTPException(401, "Invalid API key")
    # The webhook has already checked its own key capability and printer scope.
    return RowVisibility(visibility.user, None, True)


# Webhook endpoints


@router.post("/queue/add", response_model=QueueAddResponse)
async def webhook_add_to_queue(
    data: QueueAddRequest,
    api_key: APIKey = Depends(get_api_key),
    db: AsyncSession = DB_SESSION,
):
    """Add a print to the queue via webhook.

    Requires 'can_queue' permission.
    """
    check_permission(api_key, "queue")
    check_printer_access(api_key, data.printer_id)

    auth_enabled = await is_auth_enabled(db)
    visibility = await require_queue_creation(db, None, api_key) if auth_enabled else RowVisibility(None, None, True)
    if not visibility.allows_printer(data.printer_id):
        raise HTTPException(403, "Printer access denied")

    archive = await require_archive_source(db, data.archive_id, visibility)
    if not auth_enabled and archive.printer_id is not None and api_key.printer_ids is not None:
        if archive.printer_id not in api_key.printer_ids:
            raise HTTPException(404, "Archive not found")

    # Verify printer exists
    result = await db.execute(select(Printer).where(Printer.id == data.printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    next_position = await next_queue_position(db)

    # Parse scheduled time if provided
    scheduled_time = None
    if data.scheduled_time:
        from datetime import datetime

        try:
            scheduled_time = to_naive_utc(datetime.fromisoformat(data.scheduled_time.replace("Z", "+00:00")))
        except (ValueError, OverflowError):
            raise HTTPException(status_code=400, detail="Invalid scheduled_time format")

    plate_id = printed_plate_of_multi_plate_file(safe_join_under(settings.base_dir, archive.file_path))
    queue_item = PrintQueueItem(
        printer_id=data.printer_id,
        archive_id=data.archive_id,
        project_id=data.project_id,
        created_by_id=visibility.user.id if visibility.user else None,
        position=next_position,
        scheduled_time=scheduled_time,
        require_previous_success=data.require_previous_success,
        auto_off_after=data.auto_off_after,
        plate_id=plate_id,
        ams_mapping=saved_slicer_ams_mapping(archive, data.printer_id, plate_id),
        **await default_print_options(db),
    )
    db.add(queue_item)
    await db.commit()
    await db.refresh(queue_item)
    await announce_queue_jobs_added([queue_item.id])

    return QueueAddResponse(
        id=queue_item.id,
        archive_id=queue_item.archive_id,
        printer_id=queue_item.printer_id,
        position=queue_item.position,
        status=queue_item.status,
        message=f"Added to queue at position {queue_item.position}",
    )


@router.post("/printer/{printer_id}/start")
async def webhook_start_print(
    printer_id: int,
    api_key: APIKey = Depends(get_api_key),
    db: AsyncSession = DB_SESSION,
):
    """Trigger the next manual-start queue item on a printer.

    Mirrors `POST /print-queue/{item_id}/start`: clears `manual_start` on
    the next pending item so the scheduler picks it up — which handles
    FTP upload, AMS mapping, and all print options (timelapse,
    bed_levelling, etc.) correctly via the queue's stored fields. The
    previous implementation called `printer_manager.start_print()`
    directly with `archive_id` as the filename arg and no print options,
    bypassing the upload step entirely and discarding the user's
    workflow choices — it 500'd before ever reaching the printer.

    Requires 'can_control_printer' permission.
    """
    check_permission(api_key, "control_printer")
    check_printer_access(api_key, printer_id)

    visibility = await _webhook_visibility(db, api_key)
    if not visibility.allows_printer(printer_id):
        raise HTTPException(403, "Printer access denied")

    # Get printer
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    owner = visibility.user
    scope = visibility.criteria(PrintQueueItem.created_by_id, Permission.QUEUE_UPDATE_ALL, Permission.QUEUE_UPDATE_OWN)
    if owner is not None and not owner.has_permission(Permission.QUEUE_UPDATE_ALL.value):
        if owner.has_permission(Permission.QUEUE_UPDATE_OWN.value):
            scope = (or_(PrintQueueItem.created_by_id == owner.id, PrintQueueItem.created_by_id.is_(None)),)

    result = await db.execute(
        select(PrintQueueItem)
        .where(
            PrintQueueItem.printer_id == printer_id,
            PrintQueueItem.status == "pending",
            *scope,
        )
        .order_by(PrintQueueItem.position)
        .limit(1)
    )
    queue_item = result.scalar_one_or_none()
    if not queue_item:
        raise HTTPException(status_code=404, detail="No pending prints in queue")

    # Recheck scope when clearing manual start, including a concurrent claim of an ownerless job.
    queue_item_id = queue_item.id
    result = await db.execute(
        update(PrintQueueItem)
        .where(
            PrintQueueItem.id == queue_item_id,
            PrintQueueItem.printer_id == printer_id,
            PrintQueueItem.status == "pending",
            *scope,
        )
        .values(
            manual_start=False,
            created_by_id=func.coalesce(PrintQueueItem.created_by_id, owner.id)
            if owner
            else PrintQueueItem.created_by_id,
        )
    )
    if result.rowcount != 1:
        raise HTTPException(409, "The queue item changed before it could start")
    await db.commit()

    logger.info("Webhook started queue item %s on printer %s", queue_item_id, printer_id)
    return {"message": "Print started", "queue_item_id": queue_item_id}


def _stop_current_print(printer_id: int) -> None:
    try:
        sent = stop_print_by_user(printer_id)
    except Exception:
        logger.exception("Could not stop printer %s through the webhook", printer_id)
        raise HTTPException(500, "Failed to stop print")
    if not sent:
        raise HTTPException(503, "Printer not connected")


@router.post("/printer/{printer_id}/stop")
async def webhook_stop_print(
    printer_id: int,
    api_key: APIKey = Depends(get_api_key),
):
    """Stop the current print on a printer.

    Requires 'can_control_printer' permission.
    """
    check_permission(api_key, "control_printer")
    check_printer_access(api_key, printer_id)

    status = printer_manager.get_status(printer_id)
    # `printer_manager.get_status(...)` returns a ``PrinterState`` dataclass
    # (see backend/app/services/bambu_mqtt.py), not a dict — `.get(...)` on it
    # raises AttributeError and surfaces as a generic 500 (#1584).
    if not status or not status.connected:
        raise HTTPException(status_code=503, detail="Printer not connected")

    if status.state not in STOPPABLE_STATES:
        raise HTTPException(status_code=409, detail="No print in progress")

    _stop_current_print(printer_id)

    return {"message": "Print stopped"}


@router.post("/printer/{printer_id}/cancel")
async def webhook_cancel_print(
    printer_id: int,
    api_key: APIKey = Depends(get_api_key),
):
    """Cancel the current print on a printer.

    Requires 'can_control_printer' permission.
    """
    check_permission(api_key, "control_printer")
    check_printer_access(api_key, printer_id)

    status = printer_manager.get_status(printer_id)
    # Same dataclass-not-dict shape as stop_print above (#1584).
    if not status or not status.connected:
        raise HTTPException(status_code=503, detail="Printer not connected")

    if status.state not in STOPPABLE_STATES:
        raise HTTPException(status_code=409, detail="No print to cancel")

    _stop_current_print(printer_id)

    return {"message": "Print cancelled"}


@router.get("/printer/{printer_id}/status", response_model=PrinterStatusResponse)
async def webhook_get_printer_status(
    printer_id: int,
    api_key: APIKey = Depends(get_api_key),
    db: AsyncSession = DB_SESSION,
):
    """Get status of a printer.

    Requires 'can_read_status' permission.
    """
    check_permission(api_key, "read_status")
    check_printer_access(api_key, printer_id)

    # Get printer
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    status = printer_manager.get_status(printer_id)

    # `printer_manager.get_status(...)` returns a ``PrinterState`` dataclass —
    # attribute access, not dict lookup. The previous `.get(...)` calls raised
    # AttributeError and surfaced as a generic 500 for any printer that
    # actually had a status row (#1584).
    if status is None:
        return PrinterStatusResponse(
            id=printer.id,
            name=printer.name,
            serial_number=printer.serial_number,
            connected=False,
            state=None,
            current_print=None,
            progress=None,
            remaining_time=None,
        )
    return PrinterStatusResponse(
        id=printer.id,
        name=printer.name,
        serial_number=printer.serial_number,
        connected=status.connected,
        state=status.state,
        current_print=status.current_print,
        progress=status.progress,
        remaining_time=status.remaining_time,
        remaining_seconds=status.remaining_time * 60 if status.remaining_time is not None else None,
        layer_num=status.layer_num,
        total_layers=status.total_layers,
        subtask_id=_job_id(status.subtask_id),
        hms_errors=hms_error_responses(status.hms_errors),
    )


@router.get("/queue", response_model=list[QueueStatusResponse])
async def webhook_get_queue_status(
    printer_id: int | None = None,
    api_key: APIKey = Depends(get_api_key),
    db: AsyncSession = DB_SESSION,
):
    """Get queue status for all printers or a specific printer.

    Requires 'can_read_status' permission.
    """
    check_permission(api_key, "read_status")
    visibility = await _webhook_visibility(db, api_key)

    # Get printers
    if printer_id:
        check_printer_access(api_key, printer_id)
        result = await db.execute(select(Printer).where(Printer.id == printer_id))
        printers = result.scalars().all()
    else:
        result = await db.execute(select(Printer))
        printers = result.scalars().all()
        # Filter by allowed printers if limited
        if api_key.printer_ids is not None:
            printers = [p for p in printers if p.id in api_key.printer_ids]

    response = []
    for printer in printers:
        if not visibility.allows_printer(printer.id):
            continue
        # Get queue items
        result = await db.execute(
            select(PrintQueueItem)
            .where(
                PrintQueueItem.printer_id == printer.id,
                PrintQueueItem.status.in_(["pending", "printing"]),
            )
            .order_by(PrintQueueItem.position)
        )
        items = result.scalars().all()

        pending_count = sum(1 for i in items if i.status == "pending")
        printing_count = sum(1 for i in items if i.status == "printing")

        response.append(
            QueueStatusResponse(
                printer_id=printer.id,
                printer_name=printer.name,
                pending=pending_count,
                printing=printing_count,
                items=[
                    {
                        "id": item.id,
                        "archive_id": item.archive_id,
                        "position": item.position,
                        "status": item.status,
                    }
                    for item in items
                    if visibility.can_access_owner(
                        item.created_by_id, Permission.QUEUE_READ_ALL, Permission.QUEUE_READ_OWN
                    )
                ],
            )
        )

    return response
