"""Printer-grant lifecycle: null is unrestricted; explicit empty is deny-all."""

from fastapi import HTTPException
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.printer import Printer
from backend.app.models.user import User

_SCOPE_MARKER = "migration_user_printer_scope_deny_all_v1"


async def migrate_user_printer_scope(conn) -> None:
    """Normalize historical empty scopes exactly once, in the startup transaction."""
    # Claim before normalizing. ON CONFLICT serializes concurrent startups on PG;
    # marker and conversion commit together, and later deny-all [] is untouched.
    claimed = await conn.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, 'true') ON CONFLICT (key) DO NOTHING RETURNING key"),
        {"key": _SCOPE_MARKER},
    )
    if claimed.scalar_one_or_none() is not None:
        columns = await conn.run_sync(lambda sync: {column["name"] for column in inspect(sync).get_columns("users")})
        if "allowed_printer_ids" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN allowed_printer_ids JSON"))
        column = "allowed_printer_ids" if conn.dialect.name == "sqlite" else "allowed_printer_ids::text"
        await conn.execute(text(f"UPDATE users SET allowed_printer_ids = NULL WHERE {column} = '[]'"))


async def validate_printer_grants(db: AsyncSession, printer_ids: list[int] | None) -> None:
    """Reject stale grants and lock existing printers until the user write commits."""
    if not printer_ids:
        return
    requested = set(printer_ids)
    existing = set(
        (
            await db.scalars(select(Printer.id).where(Printer.id.in_(requested)).order_by(Printer.id).with_for_update())
        ).all()
    )
    if existing != requested:
        raise HTTPException(400, "One or more printer IDs are invalid")


async def remove_printer_grants(db: AsyncSession, printer_id: int) -> None:
    """Prune deleted IDs atomically; removing the last grant persists deny-all []."""
    owners = (
        await db.scalars(
            select(User)
            .where(User.allowed_printer_ids.is_not(None))
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    for owner in owners:
        if owner.allowed_printer_ids is not None and printer_id in owner.allowed_printer_ids:
            owner.allowed_printer_ids = [id_ for id_ in owner.allowed_printer_ids if id_ != printer_id]
