"""Upgrade legacy Spoolman slot constraints without losing assignments."""

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)


async def widen_spoolman_slot_ams_id_range(conn, _safe_execute, is_sqlite) -> None:
    """Widen ck_ams_id_range on spoolman_slot_assignments to admit AMS-HT (#1274).

    Old formula: (ams_id >= 0 AND ams_id <= 7) OR ams_id = 255
    New formula: (ams_id >= 0 AND ams_id <= 7) OR (ams_id >= 128 AND ams_id <= 191) OR ams_id = 255

    The H2C/H2D AMS-HT reports ams_id 128+. The old constraint rejected every
    AMS-HT slot link with `IntegrityError: CHECK constraint failed: ck_ams_id_range`.

    PostgreSQL: DROP CONSTRAINT IF EXISTS + ADD new formula via _safe_execute.
    SQLite: table recreation when the old (narrower) formula is detected in
    sqlite_master. Fresh installs already have the widened constraint from
    the CREATE TABLE migration above.
    """
    _NEW_FORMULA = "(ams_id >= 0 AND ams_id <= 7) OR (ams_id >= 128 AND ams_id <= 191) OR ams_id = 255"
    _CONSTRAINT_NAME = "ck_ams_id_range"

    if not is_sqlite():
        await _safe_execute(
            conn,
            f"ALTER TABLE spoolman_slot_assignments DROP CONSTRAINT IF EXISTS {_CONSTRAINT_NAME}",
        )
        await _safe_execute(
            conn,
            f"ALTER TABLE spoolman_slot_assignments ADD CONSTRAINT {_CONSTRAINT_NAME} CHECK ({_NEW_FORMULA})",
        )
        return

    row = (
        await conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='spoolman_slot_assignments'")
        )
    ).fetchone()
    if not row:
        return
    sql = row[0] or ""
    # Already widened by an earlier run or by the fresh-install CREATE TABLE above.
    if "ams_id >= 128" in sql:
        return
    # Pre-migration table without any CHECK constraint at all → leave alone;
    # the app-level validation handles correctness and we don't risk a
    # destructive table rebuild for a constraint that isn't blocking anyone.
    if "ck_ams_id_range" not in sql and "ams_id <= 7" not in sql:
        return

    try:
        async with conn.begin_nested():
            await conn.execute(text("DROP TABLE IF EXISTS spoolman_slot_assignments_v2"))
            await conn.execute(
                text(
                    "CREATE TABLE spoolman_slot_assignments_v2 ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "printer_id INTEGER NOT NULL REFERENCES printers(id) ON DELETE CASCADE, "
                    f"ams_id INTEGER NOT NULL CHECK ({_NEW_FORMULA}), "
                    "tray_id INTEGER NOT NULL CHECK (tray_id >= 0 AND tray_id <= 3), "
                    "spoolman_spool_id INTEGER NOT NULL, "
                    "assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "CONSTRAINT uq_slot_assignment UNIQUE(printer_id, ams_id, tray_id)"
                    ")"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO spoolman_slot_assignments_v2 "
                    "(id, printer_id, ams_id, tray_id, spoolman_spool_id, assigned_at) "
                    "SELECT id, printer_id, ams_id, tray_id, spoolman_spool_id, assigned_at "
                    "FROM spoolman_slot_assignments"
                )
            )
            original = (await conn.execute(text("SELECT count(*) FROM spoolman_slot_assignments"))).scalar_one()
            copied = (await conn.execute(text("SELECT count(*) FROM spoolman_slot_assignments_v2"))).scalar_one()
            if copied != original:
                raise RuntimeError(
                    f"spoolman_slot_assignments migration: row count mismatch after copy "
                    f"({original} in source, {copied} in copy)"
                )
            await conn.execute(text("DROP TABLE spoolman_slot_assignments"))
            await conn.execute(text("ALTER TABLE spoolman_slot_assignments_v2 RENAME TO spoolman_slot_assignments"))
            # The index sits on the renamed table; recreate it idempotently
            # to handle older sqlite versions that don't auto-rename indexes.
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_slot_assignment_spool "
                    "ON spoolman_slot_assignments (spoolman_spool_id)"
                )
            )
    except Exception as exc:
        logger.error(
            "spoolman_slot_assignments ck_ams_id_range widening (SQLite table recreation) FAILED: %s",
            exc,
            exc_info=True,
        )
        raise
