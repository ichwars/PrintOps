from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import DateTime, cast, literal, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from backend.app.models.small_part import SmallPart
from backend.app.models.spool import Spool
from backend.app.models.warehouse_article import WarehouseArticle


def stock_timestamp_parameter(session: AsyncSession, value: datetime) -> datetime | ColumnElement[datetime]:
    if session.get_bind().dialect.name == "postgresql":
        # Bind the offset as part of the string so the engine's legacy naive-datetime
        # handling cannot reinterpret this value in the process time zone.
        return cast(literal(value.isoformat()), DateTime(timezone=True))
    return value


async def mark_checked(
    session: AsyncSession,
    model: type[Spool] | type[SmallPart] | type[WarehouseArticle],
    ids: list[int],
    checked_at: datetime,
    *conditions,
) -> None:
    timestamp = stock_timestamp_parameter(session, checked_at)
    identifiers = sorted(set(ids))
    for offset in range(0, len(identifiers), 500):
        chunk = identifiers[offset : offset + 500]
        updated = await session.scalars(
            update(model)
            .where(model.id.in_(chunk), *conditions)
            .values(stock_checked_at=timestamp, updated_at=model.updated_at)
            .returning(model.id)
        )
        if len(updated.all()) != len(chunk):
            await session.rollback()
            raise HTTPException(409, detail={"code": "stock_check_unavailable"})
