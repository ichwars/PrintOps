"""Schema migration owned by the active-print tracking feature."""

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError


async def migrate_active_print_spoolman(conn, safe_execute, sqlite: bool, logger) -> None:
    """Create and upgrade the short-lived Spoolman tracking table."""
    await safe_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS active_print_spoolman (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printer_id INTEGER NOT NULL REFERENCES printers(id) ON DELETE CASCADE,
            archive_id INTEGER NOT NULL REFERENCES print_archives(id) ON DELETE CASCADE,
            filament_usage TEXT,
            ams_trays TEXT NOT NULL,
            slot_to_tray TEXT,
            layer_usage TEXT,
            filament_properties TEXT,
            tray_remain_start TEXT,
            tray_now_at_start INTEGER,
            UNIQUE(printer_id, archive_id)
        )
        """
        if sqlite
        else """
        CREATE TABLE IF NOT EXISTS active_print_spoolman (
            id SERIAL PRIMARY KEY,
            printer_id INTEGER NOT NULL REFERENCES printers(id) ON DELETE CASCADE,
            archive_id INTEGER NOT NULL REFERENCES print_archives(id) ON DELETE CASCADE,
            filament_usage TEXT,
            ams_trays TEXT NOT NULL,
            slot_to_tray TEXT,
            layer_usage TEXT,
            filament_properties TEXT,
            tray_remain_start TEXT,
            tray_now_at_start INTEGER,
            UNIQUE(printer_id, archive_id)
        )
        """,
    )
    await safe_execute(conn, "ALTER TABLE active_print_spoolman ADD COLUMN tray_remain_start TEXT")
    await safe_execute(
        conn,
        "ALTER TABLE active_print_spoolman ADD COLUMN tray_now_at_start INTEGER"
        if sqlite
        else "ALTER TABLE active_print_spoolman ADD COLUMN IF NOT EXISTS tray_now_at_start INTEGER",
    )
    if sqlite:
        await _relax_sqlite_filament_usage(conn, logger)
    else:
        await safe_execute(conn, "ALTER TABLE active_print_spoolman ALTER COLUMN filament_usage DROP NOT NULL")
    await safe_execute(
        conn,
        "ALTER TABLE active_print_sessions ADD COLUMN subtask_id VARCHAR"
        if sqlite
        else "ALTER TABLE active_print_sessions ADD COLUMN IF NOT EXISTS subtask_id VARCHAR",
    )


async def _relax_sqlite_filament_usage(conn, logger) -> None:
    """Make the legacy filament_usage column nullable without rebuilding."""
    try:
        result = await conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='active_print_spoolman'")
        )
        table_sql = result.scalar()
        if not table_sql or "filament_usage TEXT NOT NULL" not in table_sql:
            return
        version_result = await conn.execute(text("PRAGMA schema_version"))
        schema_version = version_result.scalar() or 0
        await conn.execute(text("PRAGMA writable_schema = ON"))
        await conn.execute(
            text(
                "UPDATE sqlite_master "
                "SET sql = replace(sql, 'filament_usage TEXT NOT NULL', 'filament_usage TEXT') "
                "WHERE type='table' AND name='active_print_spoolman'"
            )
        )
        await conn.execute(text(f"PRAGMA schema_version = {schema_version + 1}"))
        await conn.execute(text("PRAGMA writable_schema = OFF"))
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "Could not relax active_print_spoolman.filament_usage NOT NULL via writable_schema: %s — "
            "no-3MF Spoolman fallback will be a no-op on this install",
            exc,
        )
