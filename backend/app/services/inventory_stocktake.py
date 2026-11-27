from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.small_part import SmallPart
from backend.app.models.spool import Spool
from backend.app.models.warehouse_article import WarehouseArticle


async def mark_checked(
    session: AsyncSession,
    model: type[Spool] | type[SmallPart] | type[WarehouseArticle],
    ids: list[int],
    checked_at: datetime,
    *conditions,
) -> None:
    identifiers = sorted(set(ids))
    for offset in range(0, len(identifiers), 500):
        chunk = identifiers[offset : offset + 500]
        updated = await session.scalars(
            update(model)
            .where(model.id.in_(chunk), *conditions)
            .values(stock_checked_at=checked_at, updated_at=model.updated_at)
            .returning(model.id)
        )
        if len(updated.all()) != len(chunk):
            await session.rollback()
            raise HTTPException(409, detail={"code": "stock_check_unavailable"})
