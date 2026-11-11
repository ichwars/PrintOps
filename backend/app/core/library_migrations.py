"""Data backfills owned by the library domain."""

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.app.utils.safe_path import PathTraversalError, safe_join_under
from backend.app.utils.threemf_tools import carries_gcode, inspect_3mf_gcode

logger = logging.getLogger(__name__)


async def repair_compound_3mf_library_types(conn: AsyncConnection, base_dir: Path) -> None:
    """Repair local rows previously marked as sliced from a compound filename."""
    flag = "_backfill_3435_unsliced_gcode_3mf_type_done"
    async with conn.begin_nested():
        if await conn.scalar(text('SELECT value FROM settings WHERE "key" = :key'), {"key": flag}):
            return

        rows = await conn.execute(
            text(
                "SELECT id, filename, file_path, file_type FROM library_files "
                "WHERE (file_type = 'gcode.3mf' OR "
                "(file_type = '3mf' AND lower(filename) LIKE '%.gcode.3mf')) "
                "AND file_path IS NOT NULL AND file_path <> '' "
                "AND (is_external IS NULL OR is_external = :external)"
            ),
            {"external": False},
        )
        reclassified = 0
        for row in rows:
            path = Path(row.file_path)
            if not path.is_absolute():
                try:
                    path = safe_join_under(base_dir, row.file_path, http=False)
                except (PathTraversalError, OSError, RuntimeError):
                    continue
            # SEC-PATH-OK: legacy internal rows can store absolute library paths.
            has_gcode = inspect_3mf_gcode(path)
            if has_gcode is None:
                # Retain the original #1600 fallback for older unreadable rows.
                if not (row.filename or "").lower().endswith(".gcode.3mf"):
                    continue
                has_gcode = True
            file_type = "gcode.3mf" if has_gcode else "3mf"
            if file_type == row.file_type:
                continue
            await conn.execute(
                text("UPDATE library_files SET file_type = :file_type WHERE id = :id"),
                {"file_type": file_type, "id": row.id},
            )
            reclassified += 1

        if reclassified:
            logger.info("Reclassified %d local library 3MF file(s)", reclassified)
        await conn.execute(
            text('INSERT INTO settings ("key", value) VALUES (:key, :value)'),
            {"key": flag, "value": "true"},
        )


async def reclassify_sliced_3mf_library_files(conn: AsyncConnection, base_dir: Path | str) -> None:
    """Repair existing internal 3MF rows classified from names alone (#132).

    This is deliberately one-shot: genuine source 3MF files remain candidates
    forever. External rows are left to their explicit folder scan so startup
    never blocks on a slow or unavailable mount.
    """
    flag = "_backfill_132_sliced_3mf_type_done"

    async with conn.begin_nested():
        already_done = (
            await conn.execute(text('SELECT value FROM settings WHERE "key" = :key'), {"key": flag})
        ).scalar_one_or_none()
        if already_done:
            return

        rows = (
            await conn.execute(
                text(
                    # Do not filter on deleted_at: this pass runs before that
                    # legacy column is added. Trashed rows still point at
                    # managed bytes and are safe to classify before restore.
                    "SELECT id, file_path FROM library_files "
                    "WHERE file_type IN ('3mf', 'model') "
                    "AND lower(file_path) LIKE '%.3mf' "
                    "AND file_path IS NOT NULL AND file_path <> '' "
                    "AND (is_external IS NULL OR is_external = :is_external)"
                ),
                {"is_external": False},
            )
        ).fetchall()

        reclassified = 0
        root = Path(base_dir)
        for row in rows:
            path = Path(row.file_path)
            if not path.is_absolute():
                path = root / path
            if not carries_gcode(path):
                continue
            await conn.execute(
                text("UPDATE library_files SET file_type = 'gcode.3mf' WHERE id = :id"),
                {"id": row.id},
            )
            reclassified += 1

        if reclassified:
            logger.info("Issue #132: reclassified %d sliced 3MF library file(s)", reclassified)

        await conn.execute(
            text('INSERT INTO settings ("key", value) VALUES (:key, :value)'),
            {"key": flag, "value": "true"},
        )
