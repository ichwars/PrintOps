"""Explicit app-message authorization and a database-serialized sliding quota."""

import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.app.models.api_key import AppMessageQuota
from backend.app.models.notification import NotificationProvider
from backend.app.models.user import User


async def validate_notification_owner(db, key):
    owner = await db.get(User, key.user_id) if key.user_id is not None else None
    if (
        owner is None
        or not owner.is_active
        or not key.notification_owner_identity
        or key.notification_owner_identity != owner.connected_identity
    ):
        raise HTTPException(403, "Notification scope requires its original active owner; recreate the API key")
    return owner


async def eligible_channels(db, key, owner, printer_id=None):
    scopes = [set(ids) for ids in (key.printer_ids, owner.allowed_printer_ids) if ids is not None]
    allowed = set.intersection(*scopes) if scopes else None
    if printer_id is not None and allowed is not None and printer_id not in allowed:
        raise HTTPException(403, "Printer outside API key or owner scope")
    query = select(NotificationProvider).where(
        NotificationProvider.enabled.is_(True), NotificationProvider.on_app_message.is_(True)
    )
    if printer_id is not None:
        from backend.app.models.printer import Printer

        if await db.get(Printer, printer_id) is None:
            raise HTTPException(404, "Printer not found")
        query = query.where(
            (NotificationProvider.printer_id.is_(None)) | (NotificationProvider.printer_id == printer_id)
        )
    elif allowed is not None:
        query = query.where(NotificationProvider.printer_id.in_(allowed))
    else:
        query = query.where(NotificationProvider.printer_id.is_(None))
    return list(await db.scalars(query.order_by(NotificationProvider.id)))


async def consume_quota(db, key):
    """Serialize on the key row on SQLite and PostgreSQL, then commit before I/O.

    A no-op conflict UPDATE obtains the database write/row lock before reading
    usage. No process-local state is involved. Each key stores at most 20 times.
    """
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    statement = insert(AppMessageQuota).values(key_hash=key.key_hash, key_id=key.id, timestamps=[])
    await db.execute(
        statement.on_conflict_do_update(index_elements=[AppMessageQuota.key_hash], set_={"key_id": key.id})
    )
    quota = await db.scalar(
        select(AppMessageQuota)
        .where(AppMessageQuota.key_hash == key.key_hash)
        .execution_options(populate_existing=True)
    )
    now = time.time()
    timestamps = [stamp for stamp in quota.timestamps if stamp > now - 60]
    if len(timestamps) >= 20:
        await db.commit()
        raise HTTPException(429, "At most 20 app messages per 60 seconds", headers={"Retry-After": "60"})
    quota.timestamps = timestamps + [now]
    await db.commit()
