from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.websocket import ws_manager
from backend.app.models.spool import Spool
from backend.app.models.user import User
from backend.app.schemas.inventory_stocktake import StockCheckRead, StockCheckRequest
from backend.app.services import inventory_stocktake

router = APIRouter()


@router.post("/spools/stock-check", response_model=StockCheckRead)
async def confirm_spool_stock_check(
    data: StockCheckRequest,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
) -> StockCheckRead:
    checked_at = datetime.now(timezone.utc)
    await inventory_stocktake.mark_checked(db, Spool, data.ids, checked_at, Spool.archived_at.is_(None))
    await db.commit()
    await ws_manager.broadcast({"type": "inventory_changed"})
    return StockCheckRead(stock_checked_at=checked_at)
