"""Choose an existing archive for the exact file selected by a queue dispatch."""

import asyncio
from pathlib import Path
from weakref import WeakValueDictionary

from sqlalchemy import or_, select, text

from backend.app.core.config import settings
from backend.app.models.archive import PrintArchive
from backend.app.services.archive import ArchiveService
from backend.app.utils.safe_path import PathTraversalError, safe_join_under

_locks: WeakValueDictionary[tuple, asyncio.Lock] = WeakValueDictionary()


def _matches_archived_bytes(file_path: str, content_hash: str) -> bool:
    if not file_path:
        return False
    try:
        archive_file = safe_join_under(settings.base_dir, file_path, http=False)
        return archive_file.is_file() and ArchiveService.compute_file_hash(archive_file) == content_hash
    except (PathTraversalError, OSError):
        return False


async def archive_library_dispatch(db, item, source_file: Path, filename: str):
    """Serialize reuse/creation through the archive commit for an identical source."""
    content_hash = await asyncio.to_thread(ArchiveService.compute_file_hash, source_file)
    identity = content_hash, item.created_by_id, item.project_id
    lock = _locks.setdefault(identity, asyncio.Lock())
    async with lock:
        if db.get_bind().dialect.name == "postgresql":
            await db.execute(
                text("SELECT pg_advisory_xact_lock(3375, hashtext(:identity))"),
                {"identity": f"{content_hash}:{item.created_by_id}:{item.project_id}"},
            )
        candidates = await db.scalars(
            select(PrintArchive)
            .where(
                PrintArchive.content_hash == content_hash,
                PrintArchive.created_by_id.is_not_distinct_from(item.created_by_id),
                PrintArchive.project_id.is_not_distinct_from(item.project_id),
                PrintArchive.deleted_at.is_(None),
                or_(
                    PrintArchive.source_library_file_id == item.library_file_id,
                    PrintArchive.source_library_file_id.is_(None),
                ),
            )
            .order_by(PrintArchive.id.desc())
            .with_for_update()
        )
        for archive in candidates:
            if await asyncio.to_thread(_matches_archived_bytes, archive.file_path, content_hash):
                if archive.source_library_file_id is None:
                    archive.source_library_file_id = item.library_file_id
                await db.commit()
                return archive

        return await ArchiveService(db).archive_print(
            printer_id=item.printer_id,
            source_file=source_file,
            original_filename=filename,
            created_by_id=item.created_by_id,
            project_id=item.project_id,
            plate_id=item.plate_id,
            source_library_file_id=item.library_file_id,
        )
