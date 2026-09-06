"""Conservative one-shot repair for plate-scoped archive metadata (#138)."""

import logging
from pathlib import Path

from sqlalchemy import text

from backend.app.core.config import settings
from backend.app.utils.threemf_tools import (
    extract_bed_temperature_from_3mf,
    extract_bed_type_from_3mf,
    extract_layer_height_from_3mf,
)

logger = logging.getLogger(__name__)
_FLAG = "_printops_138_archive_metadata_done"


async def _backfill_plate_ids(conn) -> None:
    """Recover only a single unambiguous plate from linked queue history."""
    rows = (
        await conn.execute(
            text(
                "SELECT archive_id, MIN(plate_id) AS plate_id FROM print_queue "
                "WHERE archive_id IS NOT NULL AND plate_id IS NOT NULL GROUP BY archive_id "
                "HAVING COUNT(DISTINCT plate_id) = 1"
            )
        )
    ).fetchall()
    for archive_id, plate_id in rows:
        await conn.execute(
            text("UPDATE print_archives SET plate_id = :plate WHERE id = :id AND plate_id IS NULL"),
            {"plate": plate_id, "id": archive_id},
        )


async def _prepare_sqlite_fts(conn) -> None:
    if conn.dialect.name != "sqlite":
        return
    exists = (await conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='archive_fts'"))).first()
    if exists:
        await conn.execute(text("INSERT INTO archive_fts(archive_fts) VALUES('rebuild')"))


async def repair_archive_plate_metadata(conn) -> None:
    """Repair evidence-backed plate fields without overwriting user values."""
    async with conn.begin_nested():
        done = (
            await conn.execute(text('SELECT value FROM settings WHERE "key" = :key'), {"key": _FLAG})
        ).scalar_one_or_none()
        if done is not None:
            return

        await _prepare_sqlite_fts(conn)
        await _backfill_plate_ids(conn)
        rows = (
            await conn.execute(
                text(
                    "SELECT id, file_path, plate_id, bed_temperature FROM print_archives "
                    "WHERE file_path IS NOT NULL AND file_path != ''"
                )
            )
        ).fetchall()
        repaired = 0
        for archive_id, file_path, plate_id, bed_temperature in rows:
            if plate_id is None:
                continue
            try:
                path = Path(file_path)
                if not path.is_absolute():
                    path = settings.base_dir / path
                if not path.is_file():
                    continue
                values = {
                    "layer": extract_layer_height_from_3mf(path, plate_id),
                    "bed_type": extract_bed_type_from_3mf(path, plate_id),
                    "bed_temp": None
                    if bed_temperature is not None
                    else extract_bed_temperature_from_3mf(path, plate_id),
                }
                if not any(value is not None for value in values.values()):
                    continue
                await conn.execute(
                    text(
                        "UPDATE print_archives SET "
                        "layer_height = COALESCE(:layer, layer_height), "
                        "bed_type = COALESCE(:bed_type, bed_type), "
                        "bed_temperature = COALESCE(bed_temperature, :bed_temp) WHERE id = :id"
                    ),
                    {**values, "id": archive_id},
                )
                repaired += 1
            except Exception as exc:
                logger.warning("[#138] archive %s metadata repair skipped: %s", archive_id, exc)

        await conn.execute(
            text('INSERT INTO settings ("key", value) VALUES (:key, :value)'),
            {"key": _FLAG, "value": "true"},
        )
        if repaired:
            logger.info("[#138] repaired plate metadata for %d archive(s)", repaired)
