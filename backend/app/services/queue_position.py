"""One transaction-serialized position sequence for every pending queue item."""

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import user_can_access_printer
from backend.app.models.api_key import APIKey
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.user import User
from backend.app.schemas.print_queue import PrintQueueReorderItem


async def lock_queue_positions(db: AsyncSession) -> None:
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(1625, :k)"), {"k": 0})


async def max_queue_position(db: AsyncSession) -> int:
    result = await db.execute(select(func.max(PrintQueueItem.position)).where(PrintQueueItem.status == "pending"))
    return result.scalar() or 0


async def next_queue_position(db: AsyncSession) -> int:
    await lock_queue_positions(db)
    return await max_queue_position(db) + 1


async def reorder_queue_positions(
    db: AsyncSession,
    items: list[PrintQueueReorderItem],
    user: User | None,
    api_key: APIKey | None,
) -> None:
    """Reorder authorized pending IDs within their existing global slots."""
    requested_ids = {item.id for item in items}
    if len(requested_ids) != len(items):
        raise HTTPException(422, "Duplicate queue item IDs in reorder request")
    await lock_queue_positions(db)
    pending = (
        (
            await db.execute(
                select(PrintQueueItem)
                .where(PrintQueueItem.status == "pending")
                .order_by(PrintQueueItem.position, PrintQueueItem.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    selected = {
        item.id: item
        for item in pending
        if item.id in requested_ids
        and item.dispatching_at is None
        and user_can_access_printer(user, item.printer_id)
        and (api_key is None or api_key.printer_ids is None or item.printer_id in api_key.printer_ids)
    }
    # A filtered list supplies local ranks, not absolute queue positions.
    # Reuse only the selected IDs' slots; all omitted rows keep their positions.
    slots = [item.position for item in pending if item.id in selected]
    if len(selected) == len(pending):
        slots = list(range(1, len(pending) + 1))
    ordered = [selected[item.id] for item in sorted(items, key=lambda item: item.position) if item.id in selected]
    changes = [
        (item.id, item.position, item.printer_id, position) for item, position in zip(ordered, slots, strict=True)
    ]
    for item_id, old_position, printer_id, position in changes:
        if old_position == position:
            continue
        result = await db.execute(
            update(PrintQueueItem)
            .where(
                PrintQueueItem.id == item_id,
                PrintQueueItem.position == old_position,
                PrintQueueItem.printer_id == printer_id,
                PrintQueueItem.status == "pending",
                PrintQueueItem.dispatching_at.is_(None),
            )
            .values(position=position)
        )
        if not result.rowcount:
            await db.rollback()
            raise HTTPException(409, "Queue changed during reorder; refresh and retry")
