"""Reconcile in-flight print and slicer work when its account is deleted."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.user import User


async def existing_print_owner_id(db: AsyncSession, user_id: int | None) -> int | None:
    if user_id is None:
        return None
    return await db.scalar(select(User.id).where(User.id == user_id).with_for_update(read=True, key_share=True))


async def queue_owner_id(db: AsyncSession, queue_item_id: int) -> int | None:
    return await db.scalar(select(PrintQueueItem.created_by_id).where(PrintQueueItem.id == queue_item_id))


def forget_user_print_ownership(user_id: int) -> None:
    from backend.app.main import _expected_print_creators
    from backend.app.services.printer_manager import printer_manager
    from backend.app.services.slice_dispatch import slice_dispatch

    printer_manager.forget_user(user_id)
    slice_dispatch.forget_owner(user_id)
    for key in [key for key, owner in _expected_print_creators.items() if owner == user_id]:
        del _expected_print_creators[key]
