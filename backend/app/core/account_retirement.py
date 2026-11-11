"""Retain application records while removing references to a deleted account."""

import re
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import delete, exists, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from backend.app.models.api_key import APIKey, AppMessageQuota
from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.settings import Settings
from backend.app.models.user import User

_EMAIL_2FA_KEY = re.compile(r"user_(\d+)_email_2fa_enabled")


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    id: int
    identity: str | None
    username: str
    created_at: datetime


async def hold_model_queue_jobs(db: AsyncSession | AsyncConnection, owner_condition) -> None:
    """An ownerless automatic model job could otherwise use every printer of that model."""
    await db.execute(
        update(PrintQueueItem)
        .where(
            owner_condition,
            PrintQueueItem.printer_id.is_(None),
            PrintQueueItem.target_model.is_not(None),
            PrintQueueItem.status == "pending",
            PrintQueueItem.manual_start.is_(False),
        )
        .values(manual_start=True)
    )


async def detach_user_references(db: AsyncSession | AsyncConnection, user_id: int | None = None) -> None:
    """Apply the model's SET NULL rules without touching historical timestamps."""
    actual_columns = None
    if user_id is None and isinstance(db, AsyncConnection):
        actual_columns = await db.run_sync(
            lambda connection: {
                name: {column["name"] for column in columns if column["nullable"]}
                for (_, name), columns in inspect(connection).get_multi_columns().items()
            }
        )

    for table in User.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            column = foreign_key.parent
            if foreign_key.target_fullname != "users.id" or foreign_key.ondelete != "SET NULL" or not column.nullable:
                continue
            if actual_columns is not None and column.name not in actual_columns.get(table.name, ()):
                continue
            owner = (
                column == user_id if user_id is not None else (column.is_not(None) & ~exists().where(User.id == column))
            )
            values = {other.key: other for other in table.columns if other.onupdate is not None}
            values[column.key] = None
            if table is PrintArchive.__table__ and column is table.c.created_by_id:
                values["created_by_identity"] = None
            await db.execute(update(table).where(owner).values(values))


async def repair_deleted_accounts(conn: AsyncConnection) -> None:
    """Clear orphaned MFA settings and repair old SQLite user references."""
    email_2fa_keys = await conn.scalars(
        select(Settings.key).where(Settings.key.like(r"user\_%\_email\_2fa\_enabled", escape="\\"))
    )
    user_ids = set(await conn.scalars(select(User.id)))
    orphan_settings = [
        key for key in email_2fa_keys if (match := _EMAIL_2FA_KEY.fullmatch(key)) and int(match[1]) not in user_ids
    ]
    if orphan_settings:
        await conn.execute(delete(Settings).where(Settings.key.in_(orphan_settings)))

    if conn.dialect.name != "sqlite":
        return

    queue_owner_missing = PrintQueueItem.created_by_id.is_not(None) & ~exists().where(
        User.id == PrintQueueItem.created_by_id
    )
    await hold_model_queue_jobs(conn, queue_owner_missing)
    await detach_user_references(conn)

    orphan_keys = select(APIKey.id).where(APIKey.user_id.is_not(None), ~exists().where(User.id == APIKey.user_id))
    await conn.execute(delete(AppMessageQuota).where(AppMessageQuota.key_id.in_(orphan_keys)))
    for table in User.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            if foreign_key.target_fullname == "users.id" and foreign_key.ondelete == "CASCADE":
                column = foreign_key.parent
                await conn.execute(delete(table).where(column.is_not(None), ~exists().where(User.id == column)))


def capture_account(user: User | None) -> AccountSnapshot | None:
    if user is None:
        return None
    return AccountSnapshot(user.id, user.connected_identity, user.username, user.created_at)


async def require_current_account(db: AsyncSession, account: AccountSnapshot | None) -> int | None:
    """Revalidate the originating account after slow work, before saving its results."""
    if account is None:
        return None

    from backend.app.core.user_printer_scope import prepare_printer_scope_write

    await prepare_printer_scope_write(db)
    condition = (
        User.connected_identity == account.identity
        if account.identity is not None
        else (
            User.connected_identity.is_(None)
            & (User.username == account.username)
            & (User.created_at == account.created_at)
        )
    )
    found = await db.scalar(
        select(User.id).where(User.id == account.id, User.is_active.is_(True), condition).with_for_update()
    )
    if found is None:
        raise HTTPException(401, "The account is no longer active")
    return found
