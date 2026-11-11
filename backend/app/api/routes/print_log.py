import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    OwnershipAccess,
    check_printer_access,
    require_media_token_ownership,
    require_ownership_permission,
    require_permission_with_key,
    user_can_access_printer,
)
from backend.app.core.config import settings
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import PrintLogEntry
from backend.app.schemas.print_log import PrintLogEntrySchema, PrintLogEntryUpdate, PrintLogResponse
from backend.app.services.print_log_run import project_latest_finished_run, run_visibility_conditions
from backend.app.utils.safe_path import PathTraversalError, safe_join_under

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/print-log", tags=["print-log"])


_SORTABLE_COLUMNS = {
    "date": func.coalesce(PrintLogEntry.started_at, PrintLogEntry.created_at),
    "print_name": PrintLogEntry.print_name,
    "printer": PrintLogEntry.printer_name,
    "user": PrintLogEntry.created_by_username,
    "status": PrintLogEntry.status,
    "duration": PrintLogEntry.duration_seconds,
    "completed_at": PrintLogEntry.completed_at,
    "filament": PrintLogEntry.filament_type,
    "filament_used": PrintLogEntry.filament_used_grams,
    "cost": PrintLogEntry.cost,
    "energy": PrintLogEntry.energy_kwh,
    "energy_cost": PrintLogEntry.energy_cost,
}


@router.get("/", response_model=PrintLogResponse)
async def get_print_log(
    search: str | None = None,
    printer_id: int | None = None,
    created_by_username: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="date"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: AsyncSession = DB_SESSION,
    auth_result: OwnershipAccess = Depends(
        require_ownership_permission(
            Permission.ARCHIVES_READ_ALL,
            Permission.ARCHIVES_READ_OWN,
            include_api_key=True,
        )
    ),
):
    """Get the print log."""
    visible = run_visibility_conditions(auth_result)
    query = select(PrintLogEntry).where(*visible)
    count_query = select(func.count(PrintLogEntry.id)).where(*visible)

    if printer_id is not None:
        query = query.where(PrintLogEntry.printer_id == printer_id)
        count_query = count_query.where(PrintLogEntry.printer_id == printer_id)
    if created_by_username:
        query = query.where(PrintLogEntry.created_by_username == created_by_username)
        count_query = count_query.where(PrintLogEntry.created_by_username == created_by_username)
    if status:
        query = query.where(PrintLogEntry.status == status)
        count_query = count_query.where(PrintLogEntry.status == status)
    if search:
        query = query.where(PrintLogEntry.print_name.ilike(f"%{search}%"))
        count_query = count_query.where(PrintLogEntry.print_name.ilike(f"%{search}%"))
    if date_from:
        query = query.where(PrintLogEntry.created_at >= date_from)
        count_query = count_query.where(PrintLogEntry.created_at >= date_from)
    if date_to:
        query = query.where(PrintLogEntry.created_at <= date_to)
        count_query = count_query.where(PrintLogEntry.created_at <= date_to)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    column = _SORTABLE_COLUMNS.get(sort_by)
    if column is None:
        raise HTTPException(400, f"Cannot sort by {sort_by!r}")
    ordering = column.asc() if sort_dir == "asc" else column.desc()
    query = query.order_by(nullslast(ordering), PrintLogEntry.id.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    entries = result.scalars().all()

    return PrintLogResponse(
        items=[PrintLogEntrySchema.model_validate(e) for e in entries],
        total=total,
    )


@router.get("/{entry_id}/thumbnail")
async def get_print_log_thumbnail(
    entry_id: int,
    db: AsyncSession = DB_SESSION,
    auth_result: OwnershipAccess = Depends(
        require_media_token_ownership(Permission.ARCHIVES_READ_ALL, Permission.ARCHIVES_READ_OWN, include_api_key=True)
    ),
):
    """Get the thumbnail for a print log entry.

    Requires a media token query param (?token=xxx) when auth is enabled.

    Self-heals stale entries: when thumbnail_path points to a file that no
    longer exists on disk (archive was deleted, or print failed before the
    thumbnail was ever written), NULL the path on the entry so subsequent
    page renders skip the request entirely. The frontend's <img> tag is
    gated on entry.thumbnail_path being truthy, so the next fetch of the
    log list will simply not request this thumbnail again.
    """
    user, can_read_all, api_key = auth_result
    entry = await db.get(PrintLogEntry, entry_id)
    if not entry or not entry.thumbnail_path:
        raise HTTPException(404, "Thumbnail not found")

    if not can_read_all and (user is None or entry.created_by_id != user.id):
        raise HTTPException(404, "Thumbnail not found")
    if not user_can_access_printer(user, entry.printer_id):
        raise HTTPException(404, "Thumbnail not found")

    if api_key is not None:
        check_printer_access(api_key, entry.printer_id)

    try:
        thumb_path = safe_join_under(settings.base_dir, entry.thumbnail_path, http=False)
    except PathTraversalError as error:
        raise HTTPException(404, "Thumbnail not found") from error
    if not thumb_path.exists():
        entry.thumbnail_path = None
        await db.commit()
        raise HTTPException(404, "Thumbnail file not found")

    return FileResponse(
        path=thumb_path,
        media_type="image/png",
        headers={"Cache-Control": "private, no-cache, must-revalidate"},
    )


@router.delete("/")
async def clear_print_log(
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.ARCHIVES_DELETE_ALL)),
):
    """Clear the print log.

    Only deletes log entries. Archives and queue items are never touched.
    """
    visible = run_visibility_conditions(access)
    result = await db.execute(delete(PrintLogEntry).where(*visible))
    deleted = result.rowcount
    await db.commit()

    logger.info("Print log cleared: %d entries deleted", deleted)
    return {"deleted": deleted}


@router.delete("/{entry_id}")
async def delete_print_log_entry(
    entry_id: int,
    db: AsyncSession = DB_SESSION,
    auth_result: OwnershipAccess = Depends(
        require_ownership_permission(
            Permission.ARCHIVES_DELETE_ALL,
            Permission.ARCHIVES_DELETE_OWN,
            include_api_key=True,
        )
    ),
):
    """Delete a single print-log entry (#1687).

    Removes the row entirely. Because /archives/stats aggregates over
    PrintLogEntry, the deleted row's filament / cost / duration / count
    contributions drop out of the totals in the same response cycle.
    The linked archive (if any) is untouched — the FK on the archive row
    is from PrintLogEntry, not the other way around.
    """
    entry = await db.get(PrintLogEntry, entry_id)
    if not entry or not user_can_access_printer(auth_result.user, entry.printer_id):
        raise HTTPException(404, "Print log entry not found")

    if auth_result.api_key is not None:
        check_printer_access(auth_result.api_key, entry.printer_id)

    if not auth_result.can_access_all and (auth_result.user is None or entry.created_by_id != auth_result.user.id):
        raise HTTPException(403, "You can only delete your own print log entries")

    await db.delete(entry)
    await db.commit()

    logger.info("Print log entry %d deleted", entry_id)
    return {"status": "deleted", "id": entry_id}


# Canonical failure-reason vocabulary. Mirrors the frontend dropdown in
# EditArchiveModal.tsx; the empty string is the "clear classification" value.
# The catch-all "other" is the escape hatch for failures that don't fit the
# enumerated list. Keep these two lists in sync if the EditArchiveModal options
# ever change.
_FAILURE_REASON_KEYS = frozenset(
    {
        "",
        "adhesionFailure",
        "spaghettiDetached",
        "layerShift",
        "cloggedNozzle",
        "filamentRunout",
        "warping",
        "stringing",
        "underExtrusion",
        "powerFailure",
        "userCancelled",
        "noStatusUpdate",
        "other",
    }
)

# Same status vocabulary the print-log column already filters by.
_STATUS_KEYS = frozenset({"completed", "failed", "stopped", "cancelled", "skipped"})


@router.patch("/{entry_id}", response_model=PrintLogEntrySchema)
async def update_print_log_entry(
    entry_id: int,
    update: PrintLogEntryUpdate,
    db: AsyncSession = DB_SESSION,
    auth_result: OwnershipAccess = Depends(
        require_ownership_permission(
            Permission.ARCHIVES_UPDATE_ALL,
            Permission.ARCHIVES_UPDATE_OWN,
            include_api_key=True,
        )
    ),
):
    """Edit a single Print Log row's classification (#1687 part 4, reporter
    IndividualGhost1905).

    Lets the user set ``failure_reason`` (and optionally re-classify ``status``)
    directly on a Print Log row — including orphan entries that have no
    archive to edit through. The Failure Analysis widget already groups by
    ``PrintLogEntry.failure_reason`` (see ``archives.py:1421`` for the
    archive-side mirror); this endpoint is the missing edit affordance for the
    log-side, mirror-less case.

    Ownership semantics mirror the per-row delete: archives:update_all sees
    everything; archives:update_own sees only rows it owns.
    """
    entry = await db.get(PrintLogEntry, entry_id)
    if not entry or not user_can_access_printer(auth_result.user, entry.printer_id):
        raise HTTPException(404, "Print log entry not found")

    if auth_result.api_key is not None:
        check_printer_access(auth_result.api_key, entry.printer_id)

    if not auth_result.can_access_all and (auth_result.user is None or entry.created_by_id != auth_result.user.id):
        raise HTTPException(403, "You can only update your own print log entries")

    payload = update.model_dump(exclude_unset=True)

    # Validate against the canonical vocabularies. Reject unknown values rather
    # than silently storing them — the Failure Analysis widget renders the
    # values back as i18n keys, and an unrecognised value would surface as a
    # raw string in the UI.
    if "failure_reason" in payload:
        new_reason = payload["failure_reason"] or ""
        if new_reason not in _FAILURE_REASON_KEYS:
            raise HTTPException(400, f"Unknown failure_reason: {new_reason!r}")
        # Store empty string back as NULL so the column's nullable=True intent
        # is preserved end-to-end.
        entry.failure_reason = new_reason or None

    if "status" in payload and payload["status"] is not None:
        new_status = payload["status"]
        if new_status not in _STATUS_KEYS:
            raise HTTPException(400, f"Unknown status: {new_status!r}")
        entry.status = new_status

    if entry.archive_id is not None:
        archive = await db.get(PrintArchive, entry.archive_id, with_for_update=True)
        if archive is not None:
            await project_latest_finished_run(db, archive)
    await db.commit()
    await db.refresh(entry)

    logger.info(
        "Print log entry %d updated (failure_reason=%r, status=%r)",
        entry_id,
        entry.failure_reason,
        entry.status,
    )

    return PrintLogEntrySchema.model_validate(entry)
