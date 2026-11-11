"""Keep printer-bound resources from becoming global after printer deletion."""

import json
import os
from pathlib import Path

from sqlalchemy import delete, exists, inspect, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from backend.app.core.config import settings
from backend.app.models.api_key import APIKey
from backend.app.models.notification import NotificationDigestQueue, NotificationLog, NotificationProvider
from backend.app.models.pending_upload import PendingUpload
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.models.smart_plug import SmartPlug
from backend.app.models.smart_plug_energy_snapshot import SmartPlugEnergySnapshot
from backend.app.models.telegram_quality import TelegramQualityConfig
from backend.app.models.virtual_printer import VirtualPrinter

OBICO_PRINTERS_KEY = "obico_enabled_printers"
VIRTUAL_PRINTER_MIGRATION_KEY = "_migrate_single_virtual_printer_done"
_LEGACY_TARGET_KEY = "virtual_printer_target_printer_id"


def _kept_printer_ids(printer_ids: list, existing: set[int] | None, deleting: int | None) -> list[int]:
    return [
        printer_id
        for printer_id in printer_ids
        if type(printer_id) is int and printer_id != deleting and (existing is None or printer_id in existing)
    ]


async def prune_printer_lists(db: AsyncSession | AsyncConnection, *, deleting: int | None = None) -> None:
    """Keep explicit lists, including empty lists, on deletion and after upgrades."""
    existing = set((await db.scalars(select(Printer.id))).all()) if deleting is None else None
    keys = select(APIKey.id, APIKey.printer_ids).order_by(APIKey.id).with_for_update()
    for key_id, printer_ids in (await db.execute(keys)).all():
        if isinstance(printer_ids, list):
            kept = _kept_printer_ids(printer_ids, existing, deleting)
            if kept != printer_ids:
                await db.execute(update(APIKey).where(APIKey.id == key_id).values(printer_ids=kept))
    await prune_obico_printers(db, existing=existing, deleting=deleting)


async def prune_obico_printers(
    db: AsyncSession | AsyncConnection, *, existing: set[int] | None = None, deleting: int | None = None
) -> None:
    raw = await db.scalar(select(Settings.value).where(Settings.key == OBICO_PRINTERS_KEY).with_for_update())
    if not raw:
        return
    try:
        printer_ids = json.loads(raw)
    except ValueError:
        printer_ids = None
    if existing is None and deleting is None:
        existing = set((await db.scalars(select(Printer.id))).all())
    kept = _kept_printer_ids(printer_ids, existing, deleting) if isinstance(printer_ids, list) else []
    if kept != printer_ids:
        await db.execute(
            update(Settings)
            .where(Settings.key == OBICO_PRINTERS_KEY)
            .values(value=json.dumps(kept, separators=(",", ":")))
        )


async def delete_notification_provider_rows(db: AsyncSession | AsyncConnection, provider_id: int) -> None:
    from backend.app.services.telegram_quality import invalidate_provider

    await invalidate_provider(db, provider_id)
    await db.execute(delete(TelegramQualityConfig).where(TelegramQualityConfig.provider_id == provider_id))
    await db.execute(delete(NotificationLog).where(NotificationLog.provider_id == provider_id))
    await db.execute(delete(NotificationDigestQueue).where(NotificationDigestQueue.provider_id == provider_id))
    await db.execute(delete(NotificationProvider).where(NotificationProvider.id == provider_id))


async def delete_smart_plug_rows(db: AsyncSession | AsyncConnection, plug_id: int) -> None:
    await db.execute(delete(SmartPlugEnergySnapshot).where(SmartPlugEnergySnapshot.plug_id == plug_id))
    await db.execute(delete(SmartPlug).where(SmartPlug.id == plug_id))


async def delete_virtual_printer_rows(db: AsyncSession | AsyncConnection, vp_id: int, upload_dir: Path) -> None:
    prefix = str(upload_dir) + os.sep
    await db.execute(
        update(PendingUpload)
        .where(PendingUpload.file_path.startswith(prefix, autoescape=True), PendingUpload.status == "pending")
        .values(status="discarded")
    )
    await db.execute(delete(VirtualPrinter).where(VirtualPrinter.id == vp_id))


async def clear_legacy_virtual_printer_target(
    db: AsyncSession | AsyncConnection, *, deleting: int | None = None
) -> None:
    raw = await db.scalar(select(Settings.value).where(Settings.key == _LEGACY_TARGET_KEY).with_for_update())
    if not raw:
        return
    try:
        target = int(raw)
    except ValueError:
        target = None
    if deleting is not None:
        if target != deleting:
            return
    elif target is not None and await db.scalar(select(Printer.id).where(Printer.id == target)) is not None:
        return
    await db.execute(delete(Settings).where(Settings.key == _LEGACY_TARGET_KEY))
    await db.execute(update(Settings).where(Settings.key == "virtual_printer_enabled").values(value="false"))


async def repair_deleted_printer_associations(conn: AsyncConnection) -> None:
    """Repair historical orphaned scopes and align the PostgreSQL constraints."""
    await prune_printer_lists(conn)
    await clear_legacy_virtual_printer_target(conn)

    for model, printer_column, delete_rows in (
        (NotificationProvider, NotificationProvider.printer_id, delete_notification_provider_rows),
        (SmartPlug, SmartPlug.printer_id, delete_smart_plug_rows),
        (VirtualPrinter, VirtualPrinter.target_printer_id, delete_virtual_printer_rows),
    ):
        orphaned_ids = await conn.scalars(
            select(model.id).where(printer_column.is_not(None), ~exists().where(Printer.id == printer_column))
        )
        for orphaned_id in orphaned_ids.all():
            if model is VirtualPrinter:
                upload_dir = settings.base_dir / "virtual_printer" / "uploads" / str(orphaned_id)
                await delete_virtual_printer_rows(conn, orphaned_id, upload_dir)
            else:
                await delete_rows(conn, orphaned_id)
        if conn.dialect.name == "postgresql":
            await _ensure_cascade(conn, model.__tablename__, printer_column.key)


async def _ensure_cascade(conn: AsyncConnection, table: str, column: str) -> None:
    foreign_keys = await conn.run_sync(lambda sync: inspect(sync).get_foreign_keys(table))
    quote = conn.dialect.identifier_preparer.quote_identifier
    for fk in foreign_keys:
        if fk["constrained_columns"] == [column] and fk["referred_table"] == "printers":
            if fk["options"].get("ondelete") == "CASCADE":
                return
            await conn.execute(text(f"ALTER TABLE {quote(table)} DROP CONSTRAINT {quote(fk['name'])}"))
    await conn.execute(
        text(f"ALTER TABLE {quote(table)} ADD FOREIGN KEY ({quote(column)}) REFERENCES printers(id) ON DELETE CASCADE")
    )


async def migrate_legacy_virtual_printer(conn: AsyncConnection) -> None:
    """Import legacy settings once, without recreating a deleted instance."""
    claimed = await conn.scalar(
        text("INSERT INTO settings (key, value) VALUES (:key, 'true') ON CONFLICT (key) DO NOTHING RETURNING key"),
        {"key": VIRTUAL_PRINTER_MIGRATION_KEY},
    )
    if claimed is None:
        return
    if await conn.scalar(select(VirtualPrinter.id).limit(1)) is not None:
        return
    keys = (
        "virtual_printer_enabled",
        "virtual_printer_mode",
        "virtual_printer_model",
        "virtual_printer_access_code",
        _LEGACY_TARGET_KEY,
        "virtual_printer_remote_interface_ip",
    )
    stored = dict((await conn.execute(select(Settings.key, Settings.value).where(Settings.key.in_(keys)))).all())
    if "virtual_printer_enabled" not in stored:
        return

    try:
        target = int(stored[_LEGACY_TARGET_KEY]) if stored.get(_LEGACY_TARGET_KEY) else None
    except ValueError:
        return
    if target is not None and await conn.scalar(select(Printer.id).where(Printer.id == target)) is None:
        return

    # Historical "queue" meant review. "print_queue" is today's queue mode.
    mode = stored.get("virtual_printer_mode") or "archive"
    mode = {"queue": "review", "immediate": "archive", "print_queue": "queue"}.get(mode, mode)
    await conn.execute(
        text("""
            INSERT INTO virtual_printers
                (name, enabled, mode, model, access_code, target_printer_id,
                 bind_ip, remote_interface_ip, serial_suffix, position)
            VALUES
                ('PrintOps', :enabled, :mode, :model, :access_code, :target,
                 NULL, :remote_iface, '391800001', 0)
        """),
        {
            "enabled": stored["virtual_printer_enabled"] == "true",
            "mode": mode,
            "model": stored.get("virtual_printer_model", "BL-P001"),
            "access_code": stored.get("virtual_printer_access_code"),
            "target": target,
            "remote_iface": stored.get("virtual_printer_remote_interface_ip"),
        },
    )
