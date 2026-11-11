"""Lend an earlier run's 3MF to a proven touchscreen repeat."""

import asyncio
import shutil

from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.services.running_print_archive import local_archive_file
from backend.app.services.threemf_identity import candidate_3mf_conflict, expected_plate_from_paths


async def archived_repeat_source(db, printer_id, subtask_name, gcode_file, total_layers, *, base_dir, ams_mapping=None):
    if not subtask_name or not gcode_file:
        return None
    rows = (
        (
            await db.execute(
                select(PrintArchive)
                .where(
                    PrintArchive.printer_id == printer_id,
                    PrintArchive.deleted_at.is_(None),
                    PrintArchive.file_path.is_not(None),
                    PrintArchive.file_path != "",
                )
                .order_by(PrintArchive.created_at.desc(), PrintArchive.id.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    await db.close()
    for archive in rows:
        extra = archive.extra_data if isinstance(archive.extra_data, dict) else {}
        run = extra.get("_print_data")
        if not isinstance(run, dict) or run.get("subtask_name") != subtask_name or run.get("filename") != gcode_file:
            continue
        if (
            type(total_layers) is int
            and total_layers > 0
            and archive.total_layers
            and archive.total_layers != total_layers
        ):
            continue
        path = local_archive_file(archive, base_dir)
        if path is None:
            continue
        conflict = await asyncio.to_thread(
            candidate_3mf_conflict, path, expected_plate=expected_plate_from_paths(gcode_file), ams_mapping=ams_mapping
        )
        if conflict is None:
            return archive
    return None


async def copy_repeat_source(source, destination):
    """A cancelled caller still owns cleanup after the disk worker settles."""
    if source is None:
        raise FileNotFoundError("Repeat source disappeared")
    worker = asyncio.create_task(asyncio.to_thread(shutil.copyfile, source, destination))
    try:
        await asyncio.shield(worker)
    except asyncio.CancelledError:
        try:
            await worker
        finally:
            destination.unlink(missing_ok=True)
        raise
    except OSError:
        destination.unlink(missing_ok=True)
        raise
