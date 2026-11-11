"""Estimates of each plate in an archive's actual sliced file."""

import asyncio
from pathlib import Path

from sqlalchemy import select, update

from backend.app.models.archive import PrintArchive
from backend.app.utils.safe_path import PathTraversalError, safe_join_under
from backend.app.utils.threemf_tools import extract_plate_estimates_from_3mf


def estimate_for_plate(estimates, plate_id, legacy_seconds, legacy_grams=None):
    """Use a file's totals only when there is no plate metadata."""
    if not isinstance(estimates, dict) or not estimates:
        return legacy_seconds, legacy_grams
    if plate_id is None:
        entry = next(iter(estimates.values())) if len(estimates) == 1 else None
    else:
        entry = estimates.get(str(plate_id))
    return (entry.get("seconds"), entry.get("grams")) if isinstance(entry, dict) else (None, None)


def read_archive_plate_estimates(base_dir: Path, file_path: str):
    if not file_path:
        return None
    try:
        file = safe_join_under(base_dir, file_path, http=False)
    except PathTraversalError:
        return None
    if not file.is_file():
        return None
    return extract_plate_estimates_from_3mf(file) if file.suffix.lower() == ".3mf" else {}


async def fill_archive_plate_estimates(session_factory, base_dir, batch_size=100):
    after = 0
    updated = 0
    while True:
        async with session_factory() as db:
            rows = (
                await db.execute(
                    select(PrintArchive.id, PrintArchive.file_path, PrintArchive.content_hash)
                    .where(
                        PrintArchive.id > after,
                        PrintArchive.plate_estimates.is_(None),
                        PrintArchive.deleted_at.is_(None),
                        PrintArchive.file_path != "",
                    )
                    .order_by(PrintArchive.id)
                    .limit(batch_size)
                )
            ).all()
        if not rows:
            return updated

        readings = []
        for archive_id, file_path, content_hash in rows:
            estimates = await asyncio.to_thread(read_archive_plate_estimates, base_dir, file_path)
            if estimates is not None:
                readings.append((archive_id, file_path, content_hash, estimates))
        async with session_factory() as db:
            for archive_id, file_path, content_hash, estimates in readings:
                changed = await db.execute(
                    update(PrintArchive)
                    .where(
                        PrintArchive.id == archive_id,
                        PrintArchive.file_path == file_path,
                        PrintArchive.content_hash.is_not_distinct_from(content_hash),
                        PrintArchive.plate_estimates.is_(None),
                        PrintArchive.deleted_at.is_(None),
                    )
                    .values(plate_estimates=estimates)
                )
                updated += changed.rowcount
            await db.commit()
        after = rows[-1][0]


def archive_run_estimate(archive, plate_id):
    return estimate_for_plate(
        getattr(archive, "plate_estimates", None), plate_id, archive.print_time_seconds, archive.filament_used_grams
    )


def queue_source_estimate(archive, library_file, plate_id, base_dir):
    if archive is not None:
        if archive.plate_estimates is not None:
            return archive_run_estimate(archive, plate_id)
        estimates = read_archive_plate_estimates(base_dir, archive.file_path)
        return estimate_for_plate(estimates, plate_id, archive.print_time_seconds, archive.filament_used_grams)
    if library_file is None:
        return None, None
    file = Path(library_file.file_path)
    estimates = (
        extract_plate_estimates_from_3mf(file)
        if file.is_absolute()
        else read_archive_plate_estimates(base_dir, library_file.file_path)
    )
    metadata = library_file.file_metadata or {}
    return estimate_for_plate(
        estimates, plate_id, metadata.get("print_time_seconds"), metadata.get("filament_used_grams")
    )
