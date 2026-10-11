"""One transaction-serialized position sequence for every pending queue item."""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.print_queue import PrintQueueItem


async def lock_queue_positions(db: AsyncSession) -> None:
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(1625, :k)"), {"k": 0})


async def max_queue_position(db: AsyncSession) -> int:
    result = await db.execute(select(func.max(PrintQueueItem.position)).where(PrintQueueItem.status == "pending"))
    return result.scalar() or 0


async def next_queue_position(db: AsyncSession) -> int:
    await lock_queue_positions(db)
    return await max_queue_position(db) + 1
