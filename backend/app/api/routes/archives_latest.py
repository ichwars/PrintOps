"""Recent-print summaries for printer cards."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import OwnershipAccess, require_ownership_permission
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import archive_read_criteria, resolve_row_visibility
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import PrintLogEntry

router = APIRouter(prefix="/archives", tags=["archives"])
_READ = Depends(
    require_ownership_permission(Permission.ARCHIVES_READ_ALL, Permission.ARCHIVES_READ_OWN, include_api_key=True)
)
_FINISHED = ("completed", "failed", "aborted", "stopped", "cancelled")


class PrinterLastPrint(BaseModel):
    printer_id: int
    archive_id: int
    run_id: int | None
    filename: str
    print_name: str | None
    completed_at: datetime | None


@router.get("/last-per-printer", response_model=list[PrinterLastPrint])
async def get_last_prints(access: OwnershipAccess = _READ, db: AsyncSession = DB_SESSION):
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    archive_conditions = archive_read_criteria(visibility)
    runs = (
        select(
            PrintLogEntry.printer_id.label("printer_id"),
            PrintArchive.id.label("archive_id"),
            PrintLogEntry.id.label("run_id"),
            PrintArchive.filename.label("filename"),
            func.coalesce(func.nullif(PrintLogEntry.print_name, ""), PrintArchive.print_name).label("print_name"),
            PrintLogEntry.completed_at.label("completed_at"),
            func.coalesce(PrintLogEntry.completed_at, PrintLogEntry.started_at, PrintLogEntry.created_at).label(
                "recorded_at"
            ),
        )
        .join(PrintArchive, PrintArchive.id == PrintLogEntry.archive_id)
        .where(
            PrintLogEntry.status.in_(_FINISHED),
            PrintLogEntry.printer_id.is_not(None),
            *archive_conditions,
            *visibility.criteria(
                PrintLogEntry.created_by_id,
                Permission.ARCHIVES_READ_ALL,
                Permission.ARCHIVES_READ_OWN,
                PrintLogEntry.printer_id,
            ),
        )
    )

    # Older records may have a completed archive but no separate run row.
    # An existing run controls visibility and identity for its own printer.
    history = PrintLogEntry.__table__
    has_run = (
        select(history.c.id)
        .where(
            history.c.archive_id == PrintArchive.id,
            history.c.printer_id == PrintArchive.printer_id,
            history.c.status.in_(_FINISHED),
        )
        .correlate(PrintArchive)
        .exists()
    )
    older_archives = select(
        PrintArchive.printer_id,
        PrintArchive.id,
        literal(None),
        PrintArchive.filename,
        PrintArchive.print_name,
        PrintArchive.completed_at,
        func.coalesce(PrintArchive.completed_at, PrintArchive.started_at, PrintArchive.created_at),
    ).where(
        *archive_conditions,
        *visibility.printer_criteria(PrintArchive.printer_id),
        PrintArchive.printer_id.is_not(None),
        PrintArchive.status.in_(_FINISHED),
        ~has_run,
    )

    candidates = union_all(runs, older_archives).subquery()
    ranked = select(
        candidates,
        func.row_number()
        .over(
            partition_by=candidates.c.printer_id,
            order_by=(
                candidates.c.recorded_at.desc(),
                candidates.c.run_id.desc().nulls_last(),
                candidates.c.archive_id.desc(),
            ),
        )
        .label("rank"),
    ).subquery()
    rows = (await db.execute(select(ranked).where(ranked.c.rank == 1).order_by(ranked.c.printer_id))).mappings()
    return [PrinterLastPrint.model_validate(row) for row in rows]
