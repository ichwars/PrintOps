"""Printer-grant lifecycle: null is unrestricted; explicit empty is deny-all."""

from fastapi import Depends, HTTPException
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.models.printer import Printer
from backend.app.models.user import User

USER_PRINTER_SCOPE_MIGRATION_KEY = "migration_user_printer_scope_deny_all_v1"


async def migrate_user_printer_scope(conn) -> None:
    """Normalize historical empty scopes exactly once, in the startup transaction."""
    # Claim before normalizing. ON CONFLICT serializes concurrent startups on PG;
    # marker and conversion commit together, and later deny-all [] is untouched.
    claimed = await conn.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, 'true') ON CONFLICT (key) DO NOTHING RETURNING key"),
        {"key": USER_PRINTER_SCOPE_MIGRATION_KEY},
    )
    if claimed.scalar_one_or_none() is not None:
        columns = await conn.run_sync(lambda sync: {column["name"] for column in inspect(sync).get_columns("users")})
        if "allowed_printer_ids" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN allowed_printer_ids JSON"))
        if conn.dialect.name == "sqlite":
            await conn.execute(text("UPDATE users SET allowed_printer_ids = NULL WHERE allowed_printer_ids = '[]'"))
        else:
            await conn.execute(
                text("UPDATE users SET allowed_printer_ids = NULL WHERE allowed_printer_ids::text = '[]'")
            )


async def restart_printer_scope_read(db: AsyncSession) -> bool:
    """Release SQLite read snapshots before any scope/business writes or mutex."""
    if db.get_bind().dialect.name != "sqlite":
        return False
    if db.new or db.dirty or db.deleted:
        raise RuntimeError("Printer scope write preparation must precede mutations")
    # A dependency may have established a real WAL read snapshot. Starting a
    # fresh transaction prevents SQLITE_BUSY_SNAPSHOT on read-to-write upgrade.
    await db.rollback()
    return True


async def prepare_printer_scope_write(db: AsyncSession) -> None:
    """Acquire SQLite writer exclusion before user grant validation/reads.

    PostgreSQL uses the ordered printer row locks in validation/deletion instead.
    User grant writes do not acquire the local printer-operation mutex.
    """
    if not await restart_printer_scope_read(db):
        return
    try:
        # Even a zero-row UPDATE obtains the cross-connection SQLite writer lock;
        # no printer values/timestamps change. It lasts until this write commits.
        await db.execute(text("UPDATE printers SET id = id WHERE 0"))
    except OperationalError as exc:
        await db.rollback()
        if "locked" in str(exc.orig).lower() or "busy" in str(exc.orig).lower():
            # A caller retry starts the whole request and revalidates current IDs.
            raise HTTPException(409, "Printer scope is being updated; retry the request") from exc
        raise


async def printer_scope_delete_db(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    """Reset deletion's read snapshot; let the guard acquire mutex then writer.

    Acquiring a DB writer here would invert other controls' lock order and can
    deadlock the guard's local printer mutex. The guard's first UPDATE supplies
    cross-connection writer exclusion before DELETE validates/cleans grants.
    """
    await restart_printer_scope_read(db)
    return db


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
