"""Database fencing for print writes that can race printer deletion."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.printer import Printer


async def printer_exists(db: AsyncSession, printer_id: int) -> bool:
    return await db.scalar(select(Printer.id).where(Printer.id == printer_id)) is not None


async def lock_existing_printer(db: AsyncSession, printer_id: int) -> bool:
    """Verify the printer under the same database lock its deletion needs."""
    if db.get_bind().dialect.name == "sqlite":
        result = await db.execute(
            update(Printer).where(Printer.id == printer_id).values(id=Printer.id, updated_at=Printer.updated_at)
        )
        return result.rowcount == 1
    return await db.scalar(select(Printer.id).where(Printer.id == printer_id).with_for_update()) is not None
