"""Preserve print-queue history across permanent library-file deletion (#85)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.library import LibraryFile, LibraryFolder
from backend.app.models.print_queue import PrintQueueItem
from backend.app.utils.local_time import utcnow_naive

logger = logging.getLogger(__name__)


async def release_queue_references(db: AsyncSession, file_ids: list[int]) -> int:
    """Detach queue history before permanently deleting library rows."""
    if not file_ids:
        return 0

    waiting_by_file: dict[int, list[int]] = {}
    waiting_rows = (
        await db.execute(
            select(PrintQueueItem.id, PrintQueueItem.library_file_id)
            .where(PrintQueueItem.library_file_id.in_(file_ids))
            .where(PrintQueueItem.archive_id.is_(None))
            .where(PrintQueueItem.status.in_(("pending", "skipped")))
        )
    ).all()
    for item_id, library_file_id in waiting_rows:
        waiting_by_file.setdefault(library_file_id, []).append(item_id)

    if waiting_by_file:
        names = dict(
            (
                await db.execute(
                    select(LibraryFile.id, LibraryFile.filename).where(LibraryFile.id.in_(waiting_by_file))
                )
            ).all()
        )
        now = utcnow_naive()
        for library_file_id, item_ids in waiting_by_file.items():
            await db.execute(
                update(PrintQueueItem)
                .where(PrintQueueItem.id.in_(item_ids))
                .values(
                    status="cancelled",
                    completed_at=now,
                    error_message=f"'{names.get(library_file_id, 'The library file')}' was deleted from the library",
                )
            )
        logger.info("Library delete: cancelled %d queued item(s) whose source file was removed", len(waiting_rows))

    await db.execute(
        update(PrintQueueItem).where(PrintQueueItem.library_file_id.in_(file_ids)).values(library_file_id=None)
    )
    return len(waiting_rows)


async def folder_tree_file_ids(db: AsyncSession, folder_id: int) -> list[int]:
    """Return every library-file ID in a folder subtree, including trash."""
    file_ids: list[int] = []
    pending = [folder_id]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        file_ids.extend(
            (await db.execute(select(LibraryFile.id).where(LibraryFile.folder_id == current))).scalars().all()
        )
        pending.extend(
            (await db.execute(select(LibraryFolder.id).where(LibraryFolder.parent_id == current))).scalars().all()
        )
    return file_ids


async def prepare_folder_hard_delete(db: AsyncSession, folder_id: int, *, delete_managed_files: bool) -> list[int]:
    """Collect a folder subtree and best-effort remove PrintOps-managed bytes."""
    file_ids: list[int] = []
    pending = [folder_id]
    while pending:
        current = pending.pop()
        rows = (
            await db.execute(
                select(
                    LibraryFile.id, LibraryFile.file_path, LibraryFile.thumbnail_path, LibraryFile.is_external
                ).where(LibraryFile.folder_id == current)
            )
        ).all()
        for file_id, file_path, thumbnail_path, is_external in rows:
            file_ids.append(file_id)
            if not delete_managed_files or is_external:
                continue
            for path in (file_path, thumbnail_path):
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except OSError as exc:
                    logger.warning("Failed to delete file: %s", exc)
        pending.extend(
            (await db.execute(select(LibraryFolder.id).where(LibraryFolder.parent_id == current))).scalars().all()
        )
    return file_ids


async def repoint_siblings_at_archive(
    db: AsyncSession,
    *,
    consumed_library_file_id: int,
    archive_id: int,
    dispatched_item_id: int,
) -> int:
    """Repoint waiting siblings before consuming their transient source."""
    repoint_ids = set(
        (
            await db.execute(
                select(PrintQueueItem.id)
                .where(PrintQueueItem.id != dispatched_item_id)
                .where(PrintQueueItem.library_file_id == consumed_library_file_id)
                .where(PrintQueueItem.archive_id.is_(None))
                .where(PrintQueueItem.status.in_(("pending", "printing", "skipped")))
            )
        )
        .scalars()
        .all()
    )
    if repoint_ids:
        await db.execute(
            update(PrintQueueItem)
            .where(PrintQueueItem.id.in_(repoint_ids))
            .values(archive_id=archive_id, library_file_id=None, cleanup_library_after_dispatch=False)
        )
        logger.info(
            "Queue items %s: re-pointed at archive %s before library file %s was consumed by item %s",
            sorted(repoint_ids),
            archive_id,
            consumed_library_file_id,
            dispatched_item_id,
        )

    await db.execute(
        update(PrintQueueItem)
        .where(PrintQueueItem.id != dispatched_item_id)
        .where(PrintQueueItem.library_file_id == consumed_library_file_id)
        .values(library_file_id=None)
    )
    return len(repoint_ids)


async def consume_transient_library_source(
    db: AsyncSession,
    item: PrintQueueItem,
    library_file: LibraryFile,
    archive_id: int,
) -> None:
    """Detach all queue rows before deleting a consumed transient source."""
    item.library_file_id = None
    await repoint_siblings_at_archive(
        db,
        consumed_library_file_id=library_file.id,
        archive_id=archive_id,
        dispatched_item_id=item.id,
    )
    await db.delete(library_file)


async def fail_missing_library_source(db: AsyncSession, item: PrintQueueItem) -> None:
    """Fail a queued job whose library source was trashed or deleted."""
    trashed_filename = (
        await db.execute(select(LibraryFile.filename).where(LibraryFile.id == item.library_file_id))
    ).scalar_one_or_none()
    item.status = "failed"
    item.error_message = (
        f"'{trashed_filename}' is in the library trash — restore it and queue the print again"
        if trashed_filename
        else "Library file not found — it was deleted after this job was queued"
    )
    item.completed_at = datetime.now(timezone.utc)
    await db.commit()
    logger.error(
        "Queue item %s: library file %s is %s",
        item.id,
        item.library_file_id,
        "in the trash" if trashed_filename else "gone",
    )
