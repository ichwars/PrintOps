"""Upgrade legacy Spoolman slot constraints without losing assignments."""

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)


async def widen_spoolman_slot_ams_id_range(conn, _safe_execute, is_sqlite) -> None:
    """Bring spoolman_slot_assignments' CHECKs up to the model's (AMS-HT #1274, the H3C's AMS 3H).

    ck_ams_id_range, oldest formula: (ams_id >= 0 AND ams_id <= 7) OR ams_id = 255
    #1274 added AMS-HT:  ... OR (ams_id >= 128 AND ams_id <= 191) OR ams_id = 255
    Now also the AMS 3H: ... OR ams_id = 32 OR ...
    ck_tray_id_range:    tray_id 0-3, and 4-8 for ams_id 32 / 255 (models.spoolman_slot_assignment)

    The H2C/H2D AMS-HT reports ams_id 128+. The H3C's AMS 3H is unit 32 with
    nine slots, and its per-hotend external inputs are stored as (255, 2-8).
    The old constraints rejected every such slot link with
    `IntegrityError: CHECK constraint failed`. A table whose tray check is a
    plain ``tray_id <= 8`` gets the final form too, without any row on slot 4-8
    of another unit (no AMS has such a slot).

    PostgreSQL: DROP CONSTRAINT IF EXISTS + ADD new formula via _safe_execute.
    SQLite: table recreation when an older formula is detected in
    sqlite_master. Fresh installs get the model's constraints from create_all.
    """
    from backend.app.models.spoolman_slot_assignment import AMS_ID_CHECK, TRAY_ID_CHECK

    if not is_sqlite():
        await _safe_execute(conn, "ALTER TABLE spoolman_slot_assignments DROP CONSTRAINT IF EXISTS ck_ams_id_range")
        await _safe_execute(
            conn, f"ALTER TABLE spoolman_slot_assignments ADD CONSTRAINT ck_ams_id_range CHECK ({AMS_ID_CHECK})"
        )
        await _safe_execute(conn, "ALTER TABLE spoolman_slot_assignments DROP CONSTRAINT IF EXISTS ck_tray_id_range")
        dropped = await conn.execute(
            text(f"DELETE FROM spoolman_slot_assignments WHERE NOT ({TRAY_ID_CHECK})")  # nosec B608 -- the model's constant CHECK text
        )
        if dropped.rowcount:
            logger.warning("Dropped %d Spoolman slot assignment(s) naming a slot no AMS has", dropped.rowcount)
        await _safe_execute(
            conn, f"ALTER TABLE spoolman_slot_assignments ADD CONSTRAINT ck_tray_id_range CHECK ({TRAY_ID_CHECK})"
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
    # Already in the final form (a previous start, or create_all on a fresh install).
    if "ams_id = 32" in sql and "ams_id IN (32, 255)" in sql:
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
                    "ams_id INTEGER NOT NULL, "
                    "tray_id INTEGER NOT NULL, "
                    "spoolman_spool_id INTEGER NOT NULL, "
                    "assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "CONSTRAINT uq_slot_assignment UNIQUE(printer_id, ams_id, tray_id), "
                    f"CONSTRAINT ck_ams_id_range CHECK ({AMS_ID_CHECK}), "
                    f"CONSTRAINT ck_tray_id_range CHECK ({TRAY_ID_CHECK})"
                    ")"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO spoolman_slot_assignments_v2 "  # nosec B608 -- the model's constant CHECK text
                    "(id, printer_id, ams_id, tray_id, spoolman_spool_id, assigned_at) "
                    "SELECT id, printer_id, ams_id, tray_id, spoolman_spool_id, assigned_at "
                    f"FROM spoolman_slot_assignments WHERE {TRAY_ID_CHECK}"
                )
            )
            original = (await conn.execute(text("SELECT count(*) FROM spoolman_slot_assignments"))).scalar_one()
            kept = (
                await conn.execute(
                    text(f"SELECT count(*) FROM spoolman_slot_assignments WHERE {TRAY_ID_CHECK}")  # nosec B608 -- the model's constant CHECK text
                )
            ).scalar_one()
            copied = (await conn.execute(text("SELECT count(*) FROM spoolman_slot_assignments_v2"))).scalar_one()
            if copied != kept:
                raise RuntimeError(
                    f"spoolman_slot_assignments migration: row count mismatch after copy "
                    f"({kept} to keep in source, {copied} in copy)"
                )
            if original != kept:
                logger.warning("Dropped %d Spoolman slot assignment(s) naming a slot no AMS has", original - kept)
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


async def create_slot_assignments(conn, _safe_execute, is_sqlite):
    # Migration: Create spoolman_slot_assignments table for local AMS-slot→Spoolman-spool mapping.
    # Replaces the pattern of writing spool.location in Spoolman (which polluted the
    # user-editable storage_location field in the UI).
    # ck_ams_id_range formula was widened in #1274 to admit AMS-HT (ams_id 128-191),
    # and for the H3C's AMS 3H (as models.spoolman_slot_assignment).
    await _safe_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS spoolman_slot_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printer_id INTEGER NOT NULL REFERENCES printers(id) ON DELETE CASCADE,
            ams_id INTEGER NOT NULL,
            tray_id INTEGER NOT NULL,
            spoolman_spool_id INTEGER NOT NULL,
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_slot_assignment UNIQUE(printer_id, ams_id, tray_id),
            CONSTRAINT ck_ams_id_range CHECK ((ams_id >= 0 AND ams_id <= 7) OR ams_id = 32 OR (ams_id >= 128 AND ams_id <= 191) OR ams_id = 255),
            CONSTRAINT ck_tray_id_range CHECK (tray_id >= 0 AND (tray_id <= 3 OR (ams_id IN (32, 255) AND tray_id <= 8)))
        )
        """
        if is_sqlite()
        else """
        CREATE TABLE IF NOT EXISTS spoolman_slot_assignments (
            id SERIAL PRIMARY KEY,
            printer_id INTEGER NOT NULL REFERENCES printers(id) ON DELETE CASCADE,
            ams_id INTEGER NOT NULL,
            tray_id INTEGER NOT NULL,
            spoolman_spool_id INTEGER NOT NULL,
            assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_slot_assignment UNIQUE(printer_id, ams_id, tray_id),
            CONSTRAINT ck_ams_id_range CHECK ((ams_id >= 0 AND ams_id <= 7) OR ams_id = 32 OR (ams_id >= 128 AND ams_id <= 191) OR ams_id = 255),
            CONSTRAINT ck_tray_id_range CHECK (tray_id >= 0 AND (tray_id <= 3 OR (ams_id IN (32, 255) AND tray_id <= 8)))
        )
        """,
    )
    await _safe_execute(
        conn,
        "CREATE INDEX IF NOT EXISTS ix_slot_assignment_spool ON spoolman_slot_assignments (spoolman_spool_id)",
    )
