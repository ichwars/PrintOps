"""Spool consumption history, separated by inventory source."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import OwnershipAccess, require_permission_with_key
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import resolve_row_visibility
from backend.app.models.spool import Spool
from backend.app.models.spool_usage_history import SpoolUsageHistory
from backend.app.schemas.spool_usage import SpoolUsageHistoryResponse

router = APIRouter()


InventoryUsageSource = Literal["builtin", "spoolman"]


async def _usage_scope(db, access, source: InventoryUsageSource):
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    remote_id = SpoolUsageHistory.spoolman_spool_id
    source_filter = remote_id.is_not(None) if source == "spoolman" else remote_id.is_(None)
    return source_filter, *visibility.printer_criteria(SpoolUsageHistory.printer_id)


@router.get("/spools/{spool_id}/usage", response_model=list[SpoolUsageHistoryResponse])
async def get_spool_usage_history(
    spool_id: int,
    limit: int = 50,
    source: InventoryUsageSource = "builtin",
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.INVENTORY_READ)),
):
    id_column = SpoolUsageHistory.spoolman_spool_id
    if source == "builtin":
        if await db.get(Spool, spool_id) is None:
            raise HTTPException(404, "Spool not found")
        id_column = SpoolUsageHistory.spool_id
    return list(
        await db.scalars(
            select(SpoolUsageHistory)
            .where(id_column == spool_id, *await _usage_scope(db, access, source))
            .order_by(SpoolUsageHistory.created_at.desc())
            .limit(limit)
        )
    )


@router.get("/usage", response_model=list[SpoolUsageHistoryResponse])
async def get_all_usage_history(
    limit: int = 100,
    printer_id: int | None = None,
    source: InventoryUsageSource = "builtin",
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.INVENTORY_READ)),
):
    query = select(SpoolUsageHistory).where(*await _usage_scope(db, access, source))
    if printer_id is not None:
        query = query.where(SpoolUsageHistory.printer_id == printer_id)
    return list(await db.scalars(query.order_by(SpoolUsageHistory.created_at.desc()).limit(limit)))


@router.delete("/spools/{spool_id}/usage")
async def clear_spool_usage_history(
    spool_id: int,
    source: InventoryUsageSource = "builtin",
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.INVENTORY_UPDATE)),
):
    id_column = SpoolUsageHistory.spoolman_spool_id if source == "spoolman" else SpoolUsageHistory.spool_id
    await db.execute(delete(SpoolUsageHistory).where(id_column == spool_id, *await _usage_scope(db, access, source)))
    await db.commit()
    return {"status": "cleared"}
