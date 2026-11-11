"""Combine duplicate archive files while keeping their print history and links."""

import asyncio
import logging
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, or_, select, update

from backend.app.core.config import settings
from backend.app.models.active_print_spoolman import ActivePrintSpoolman
from backend.app.models.archive import PrintArchive
from backend.app.models.archive_alias import ArchiveAlias
from backend.app.models.library import LibraryFile, LibraryFolder
from backend.app.models.pending_upload import PendingUpload
from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.print_batch import PrintBatch
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.project_bom import ProjectBOMItem
from backend.app.models.spool_usage_history import SpoolUsageHistory
from backend.app.models.telegram_quality import TelegramQualityMessage
from backend.app.services.archive import ArchiveService, lock_archive_queue_for_deletion
from backend.app.services.archive_merge_media import ArchiveMergeConflict, StagedArchiveMedia
from backend.app.services.archive_scope import whole_archive_conditions
from backend.app.services.print_log_run import project_latest_finished_run
from backend.app.utils.local_time import to_naive_utc, utcnow_naive

logger = logging.getLogger(__name__)
_GROUP_COLUMNS = (
    PrintArchive.content_hash,
    PrintArchive.created_by_id,
    PrintArchive.created_by_identity,
    PrintArchive.project_id,
)
_MOVED_REFERENCES = (
    (PrintQueueItem, PrintQueueItem.archive_id),
    (PrintBatch, PrintBatch.archive_id),
    (LibraryFolder, LibraryFolder.archive_id),
    (PendingUpload, PendingUpload.archived_id),
    (ProjectBOMItem, ProjectBOMItem.archive_id),
    (SpoolUsageHistory, SpoolUsageHistory.archive_id),
    (PipelineRun, PipelineRun.source_archive_id),
    (TelegramQualityMessage, TelegramQualityMessage.archive_id),
    (ArchiveAlias, ArchiveAlias.archive_id),
)
_ENDED = {"completed", "failed", "stopped", "cancelled", "aborted", "skipped"}
_RECENT_PRINT = timedelta(minutes=2)
_MERGING: set[int] = set()
_MEDIA_EDITS: set[int] = set()


def start_archive_media_edit(archive_id: int) -> bool:
    if archive_id in _MERGING or archive_id in _MEDIA_EDITS:
        return False
    _MEDIA_EDITS.add(archive_id)
    return True


def finish_archive_media_edit(archive_id: int) -> None:
    _MEDIA_EDITS.discard(archive_id)


def _key(archive):
    return (archive.content_hash, archive.created_by_id, archive.created_by_identity, archive.project_id)


def _candidates(access):
    return (
        PrintArchive.deleted_at.is_(None),
        PrintArchive.content_hash.is_not(None),
        PrintArchive.content_hash != "",
        *whole_archive_conditions(access),
    )


def _group_keys(access):
    return select(*_GROUP_COLUMNS).where(*_candidates(access)).group_by(*_GROUP_COLUMNS).having(func.count() > 1)


async def count_groups(db, access) -> int:
    return await db.scalar(select(func.count()).select_from(_group_keys(access).subquery())) or 0


async def resolve_alias(db, archive_id: int, access) -> int | None:
    alias = await db.get(ArchiveAlias, archive_id)
    if alias is None:
        return None
    scope = access.printer_ids
    unassigned_visible = alias.source_unassigned and (access.api_key is None or access.api_key.printer_ids is None)
    if scope is None or unassigned_visible or scope.intersection(alias.source_printer_ids):
        return alias.archive_id
    return None


async def _busy(db, ids: set[int]) -> set[int]:
    from backend.app.main import _active_prints, _expected_prints

    recent = utcnow_naive() - _RECENT_PRINT
    found = ids.intersection(_active_prints.values()) | ids.intersection(_expected_prints.values())
    queries = (
        select(PrintArchive.id).where(
            PrintArchive.id.in_(ids),
            or_(PrintArchive.status == RUN_OPEN, PrintArchive.completed_at >= recent),
        ),
        select(PrintLogEntry.archive_id)
        .where(
            PrintLogEntry.archive_id.in_(ids),
            or_(PrintLogEntry.status == RUN_OPEN, PrintLogEntry.completed_at >= recent),
        )
        .execution_options(**{INCLUDE_OPEN_RUNS: True}),
        select(PrintQueueItem.archive_id).where(
            PrintQueueItem.archive_id.in_(ids),
            or_(PrintQueueItem.status.in_(("pending", "printing")), PrintQueueItem.dispatching_at.is_not(None)),
        ),
        select(ActivePrintSpoolman.archive_id).where(ActivePrintSpoolman.archive_id.in_(ids)),
        select(PipelineRun.source_archive_id).where(
            PipelineRun.source_archive_id.in_(ids),
            PipelineRun.status.in_(("pending", "slicing", "dispatching", "queued")),
        ),
    )
    for query in queries:
        found.update(await db.scalars(query))
    return found | (ids & _MEDIA_EDITS)


async def preview_groups(db, access) -> list[dict]:
    hashes = select(_group_keys(access).subquery().c.content_hash)
    rows = await db.scalars(
        select(PrintArchive)
        .where(*_candidates(access), PrintArchive.content_hash.in_(hashes))
        .order_by(PrintArchive.id)
    )
    groups = defaultdict(list)
    for archive in rows:
        groups[_key(archive)].append(archive)
    ids = {a.id for group in groups.values() if len(group) > 1 for a in group}
    if not ids:
        return []
    busy = await _busy(db, ids) | _MERGING
    counts = dict(
        (
            await db.execute(
                select(PrintLogEntry.archive_id, func.count(PrintLogEntry.id))
                .where(PrintLogEntry.archive_id.in_(ids))
                .group_by(PrintLogEntry.archive_id)
            )
        ).all()
    )

    def brief(row):
        return {
            "id": row.id,
            "print_name": row.print_name,
            "filename": row.filename,
            "created_at": row.created_at,
            "run_count": counts.get(row.id, 0),
        }

    return [
        {
            "survivor": brief(group[0]),
            "merged": [brief(row) for row in group[1:]],
            "skipped": "busy" if any(row.id in busy for row in group) else None,
        }
        for group in groups.values()
        if len(group) > 1
    ]


def _legacy_run(row, printers):
    start, end = to_naive_utc(row.started_at), to_naive_utc(row.completed_at)
    if row.status not in _ENDED or not (start or end):
        return None
    return PrintLogEntry(
        archive_id=row.id,
        project_id=row.project_id,
        print_name=row.print_name,
        printer_id=row.printer_id,
        printer_name=printers.get(row.printer_id),
        plate_id=row.plate_id,
        subtask_id=row.subtask_id,
        status=row.status,
        started_at=start,
        completed_at=end,
        created_at=end or row.created_at,
        duration_seconds=int((end - start).total_seconds()) if start and end and end > start else None,
        filament_type=row.filament_type,
        filament_color=row.filament_color,
        filament_used_grams=row.filament_used_grams,
        cost=row.cost,
        energy_kwh=row.energy_kwh,
        energy_cost=row.energy_cost,
        failure_reason=row.failure_reason,
        quantity=row.quantity,
        confirm_requested=row.confirm_requested,
        user_verdict=row.user_verdict,
        user_verdict_source=row.user_verdict_source,
        user_verdict_at=row.user_verdict_at,
        good_quantity=row.good_quantity,
        reject_quantity=row.reject_quantity,
        created_by_id=row.created_by_id,
        thumbnail_path=row.thumbnail_path,
        photos=row.photos,
        timelapse_path=row.timelapse_path,
    )


def _single_value(rows, name):
    values = [value for row in rows if (value := getattr(row, name)) is not None and value != ""]
    if values and any(value != values[0] for value in values[1:]):
        raise ArchiveMergeConflict("conflicting_metadata")
    return values[0] if values else None


def _merge_description(rows, survivor) -> None:
    for name in ("source_library_file_id", "external_url", "makerworld_url", "designer"):
        setattr(survivor, name, _single_value(rows, name))
    notes = list(dict.fromkeys(row.notes for row in rows if row.notes))
    survivor.notes = "\n\n".join(notes) or None
    tags = dict.fromkeys(tag.strip() for row in rows for tag in (row.tags or "").split(",") if tag.strip())
    survivor.tags = ", ".join(tags) or None
    survivor.is_favorite = any(row.is_favorite for row in rows)
    ams = [row.extra_data["slicer_ams_mapping"] for row in rows if "slicer_ams_mapping" in (row.extra_data or {})]
    if ams and any(mapping != ams[0] for mapping in ams[1:]):
        raise ArchiveMergeConflict("conflicting_metadata")
    if ams:
        survivor.extra_data = {**(survivor.extra_data or {}), "slicer_ams_mapping": ams[0]}


def _move_media(staged, rows, runs, survivor):
    survivor.file_path = staged.primary(rows)
    for name in ("source_3mf_path", "f3d_path"):
        setattr(survivor, name, staged.choose_extra(rows, name))
    survivor.thumbnail_path = next((staged.copy_asset(row.thumbnail_path) for row in rows if row.thumbnail_path), None)

    photos = []
    orphan_videos = set()
    run_videos = set()
    for row in rows:
        own_runs = runs[row.id]
        photos.extend(staged.copy_photos(row, row.photos))
        archive_video = row.timelapse_path
        if archive_video and not any(run.timelapse_path == archive_video for run in own_runs):
            compatible = [run for run in own_runs if not run.timelapse_path and run.plate_id == row.timelapse_plate_id]
            if len(compatible) == 1:
                compatible[0].timelapse_path = archive_video
            else:
                orphan_videos.add(staged.copy_asset(archive_video))
        for run in own_runs:
            run.photos = staged.copy_photos(row, run.photos) or None
            photos.extend(run.photos or ())
            run.thumbnail_path = staged.copy_asset(run.thumbnail_path)
            run.timelapse_path = staged.copy_asset(run.timelapse_path)
            if run.timelapse_path:
                run_videos.add(run.timelapse_path)
            run.archive_id = survivor.id
    if len(orphan_videos | run_videos) > 1 and orphan_videos:
        raise ArchiveMergeConflict("conflicting_files")
    survivor.photos = list(dict.fromkeys(photos)) or None
    return next(iter(orphan_videos), None)


async def _copy_in_worker(staged) -> None:
    task = asyncio.create_task(asyncio.to_thread(staged.write))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


async def _commit(db) -> bool:
    task = asyncio.create_task(db.commit())
    try:
        await asyncio.shield(task)
        return False
    except asyncio.CancelledError:
        await task
        return True


async def _obsolete_folders(db, rows, survivor, archive_service):
    candidates = {archive_service._resolve_archive_dir_for_delete(row) for row in rows if row.id != survivor.id}
    for folder in candidates - {None}:
        folder = folder.resolve()
        if folder == archive_service._resolve_archive_dir_for_delete(survivor):
            continue
        relative = folder.relative_to(settings.base_dir.resolve()).as_posix()
        absolute = folder.as_posix()
        prefixes = (relative + "/", absolute + "/", relative.replace("/", "\\") + "\\")

        def uses_folder(*columns, prefixes=prefixes):
            return or_(*(column.startswith(prefix, autoescape=True) for column in columns for prefix in prefixes))

        remaining_archives = await db.scalar(
            select(PrintArchive.id)
            .where(
                PrintArchive.id.not_in({row.id for row in rows if row.id != survivor.id}),
                uses_folder(
                    PrintArchive.file_path,
                    PrintArchive.thumbnail_path,
                    PrintArchive.timelapse_path,
                    PrintArchive.source_3mf_path,
                    PrintArchive.f3d_path,
                ),
            )
            .limit(1)
        )
        remaining_runs = await db.scalar(
            select(PrintLogEntry.id)
            .where(uses_folder(PrintLogEntry.thumbnail_path, PrintLogEntry.timelapse_path))
            .limit(1)
        )
        library = await db.scalar(select(LibraryFile.id).where(uses_folder(LibraryFile.file_path)).limit(1))
        if remaining_archives is None and remaining_runs is None and library is None:
            yield folder


async def _merge_group(db, survivor_id: int, merged_ids: list[int], access):
    ids = {survivor_id, *merged_ids}
    if survivor_id in merged_ids or len(ids) != len(merged_ids) + 1:
        raise ArchiveMergeConflict("invalid_group")
    if ids & _MERGING:
        raise ArchiveMergeConflict("busy")
    _MERGING.update(ids)
    staged = None
    try:
        await lock_archive_queue_for_deletion(db, PrintArchive.id.in_(ids))
        rows = list(
            await db.scalars(
                select(PrintArchive)
                .where(PrintArchive.id.in_(ids), *_candidates(access))
                .order_by(PrintArchive.id)
                .execution_options(populate_existing=True)
            )
        )
        if len(rows) != len(ids) or rows[0].id != survivor_id or len({_key(row) for row in rows}) != 1:
            raise ArchiveMergeConflict("invalid_group")
        if await _busy(db, ids):
            raise ArchiveMergeConflict("busy")
        survivor = rows[0]
        staged = StagedArchiveMedia(survivor)
        runs = {row.id: [] for row in rows}
        for run in await db.scalars(select(PrintLogEntry).where(PrintLogEntry.archive_id.in_(ids))):
            runs[run.archive_id].append(run)
        printers = dict(
            (
                await db.execute(
                    select(Printer.id, Printer.name).where(
                        Printer.id.in_({row.printer_id for row in rows if row.printer_id is not None})
                    )
                )
            ).all()
        )
        for row in rows:
            if not runs[row.id] and (legacy := _legacy_run(row, printers)) is not None:
                db.add(legacy)
                runs[row.id].append(legacy)
        _merge_description(rows, survivor)
        orphan = _move_media(staged, rows, runs, survivor)
        await _copy_in_worker(staged)
        await db.flush()

        for model, column in _MOVED_REFERENCES:
            await db.execute(update(model).where(column.in_(merged_ids)).values({column.key: survivor.id}))
        for row in rows[1:]:
            printers_of_source = {row.printer_id, *(run.printer_id for run in runs[row.id])}
            db.add(
                ArchiveAlias(
                    merged_archive_id=row.id,
                    archive_id=survivor.id,
                    source_printer_ids=sorted(printers_of_source - {None}),
                    source_unassigned=row.printer_id is None,
                )
            )
        await project_latest_finished_run(db, survivor)
        videos = [run for own in runs.values() for run in own if run.timelapse_path]
        newest = max(
            videos, key=lambda run: (to_naive_utc(run.started_at) or to_naive_utc(run.created_at), run.id), default=None
        )
        survivor.timelapse_path = orphan or (newest.timelapse_path if newest else None)
        survivor.timelapse_plate_id = newest.plate_id if newest and not orphan else None
        obsolete = [folder async for folder in _obsolete_folders(db, rows, survivor, ArchiveService(db))]
        for row in rows[1:]:
            await db.delete(row)
        cancelled = await _commit(db)
    except BaseException:
        try:
            await db.rollback()
        finally:
            if staged is not None:
                await asyncio.to_thread(staged.undo)
        raise
    finally:
        _MERGING.difference_update(ids)
    for folder in obsolete:
        await asyncio.to_thread(staged.retire, folder)
    if cancelled:
        raise asyncio.CancelledError


async def merge_selected(db, groups, access):
    merged, skipped = [], []
    for group in groups:
        survivor_id, merged_ids = group.survivor_id, group.merged_ids
        try:
            await _merge_group(db, survivor_id, merged_ids, access)
        except ArchiveMergeConflict as conflict:
            skipped.append({"survivor_id": survivor_id, "reason": str(conflict)})
        except Exception:
            logger.exception("Could not merge archives into %s", survivor_id)
            skipped.append({"survivor_id": survivor_id, "reason": "failed"})
        else:
            merged.append({"survivor_id": survivor_id, "merged_ids": merged_ids})
    return {"merged": merged, "skipped": skipped}
