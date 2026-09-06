"""Data backfills owned by the library domain."""

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.app.utils.threemf_tools import carries_gcode

logger = logging.getLogger(__name__)


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
