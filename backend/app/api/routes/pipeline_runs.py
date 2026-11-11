"""API routes for Slicer Pipeline runs (#1425 PR B + PR C).

PR B implemented single-target dispatch: one Run-pipeline click =
  slice the source once → enqueue ONE print on ``target_printer_id``.

PR C extends this with:
  * ``copies > 1`` — slice once, enqueue N copies.
  * ``target_kind='printer_class'`` — pipeline targets a Bambu model code
    (X1C / P1S / H2D / …); orchestrator distributes copies across matching
    printers using the pipeline's ``fanout_strategy``.
  * Retry-failed runs that re-attempt only the failed/cancelled copies of
    a partial-failure run.
  * Dashboard list endpoint (``GET /pipeline-runs``) with status + pipeline
    filters and pagination.
  * WebSocket ``pipeline_run_updated`` events on state transitions so the
    dashboard refreshes live without polling.

The slice itself runs through ``slice_dispatch`` (same path as the manual
SliceModal), so the ``Slicing X — Generating G-code 75%`` toast renders
end-to-end. The slice job's id rides on the run response so the frontend
can call ``trackJob`` directly.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.cloud import resolve_api_key_cloud_owner
from backend.app.api.routes.slicer_presets import listed_stock_ref, load_stock_aliases
from backend.app.core.auth import (
    RequirePermissionIfAuthEnabled,
    check_printer_access,
    is_auth_enabled,
    resolve_optional_api_key,
)
from backend.app.core.config import settings as app_settings
from backend.app.core.database import DB_SESSION, async_session
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import (
    RowVisibility,
    archive_read_criteria,
    library_read_criteria,
    require_archive_source,
    require_library_source,
    resolve_row_visibility,
)
from backend.app.core.websocket import ws_manager
from backend.app.models.api_key import APIKey
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.pipeline_run import PipelineJob, PipelineRun
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.slicer_pipeline import SlicerPipeline
from backend.app.models.user import User
from backend.app.schemas.pipeline_run import (
    CheckEligibilityRequest,
    EligibilityIssueResponse,
    EligibilityReportResponse,
    PerPrinterReport as PerPrinterReportResponse,
    PipelineJobResponse,
    PipelineRunCreateRequest,
    PipelineRunListResponse,
    PipelineRunResponse,
)
from backend.app.schemas.slicer import PresetRef, SliceRequest, checked_bed_type
from backend.app.services.pipeline_eligibility import (
    EligibilityReport,
    check_pipeline_eligibility,
)
from backend.app.services.print_defaults import default_print_options
from backend.app.services.queue_announcements import announce_queue_jobs_added
from backend.app.services.slice_formats import (
    is_unsliceable_cad_filename,
    unsliceable_detail,
)

logger = logging.getLogger(__name__)


pipeline_run_create_router = APIRouter(prefix="/slicer-pipelines", tags=["Slicer Pipelines"])
pipeline_run_router = APIRouter(prefix="/pipeline-runs", tags=["Slicer Pipelines"])


# Helpers


def _check_pipeline_target(pipeline: SlicerPipeline, visibility: RowVisibility) -> None:
    if pipeline.target_printer_id is not None:
        if visibility.api_key is not None:
            check_printer_access(visibility.api_key, pipeline.target_printer_id)
        if not visibility.allows_printer(pipeline.target_printer_id):
            raise HTTPException(404, "Printer not found")
    elif pipeline.target_model_class and not visibility.can_use_model_target:
        raise HTTPException(403, "This API key must target a specific printer")


async def _check_pipeline_api_key_printer_access(
    db: AsyncSession,
    pipeline: SlicerPipeline,
    api_key: APIKey | None,
) -> None:
    """Fail closed when a scoped API key could dispatch outside its printers."""
    if api_key is None:
        return
    if pipeline.target_printer_id is not None:
        check_printer_access(api_key, pipeline.target_printer_id)
        return
    if pipeline.target_model_class:
        printer_ids = (
            (
                await db.execute(
                    select(Printer.id).where(func.lower(Printer.model) == (pipeline.target_model_class or "").lower())
                )
            )
            .scalars()
            .all()
        )
        for printer_id in printer_ids:
            check_printer_access(api_key, printer_id)


async def _check_run_api_key_printer_access(
    db: AsyncSession,
    run: PipelineRun,
    api_key: APIKey | None,
) -> None:
    """Check assigned jobs and any still-unassigned target before mutation."""
    if api_key is None:
        return
    jobs = (await db.execute(select(PipelineJob).where(PipelineJob.pipeline_run_id == run.id))).scalars().all()
    for job in jobs:
        if job.assigned_printer_id is not None:
            check_printer_access(api_key, job.assigned_printer_id)
    if any(job.assigned_printer_id is None for job in jobs) or not jobs:
        pipeline = (
            await db.execute(select(SlicerPipeline).where(SlicerPipeline.id == run.pipeline_id))
        ).scalar_one_or_none()
        if pipeline is not None:
            await _check_pipeline_api_key_printer_access(db, pipeline, api_key)


def _serialise_status(report: EligibilityReport) -> EligibilityReportResponse:
    return EligibilityReportResponse(
        ok=report.ok,
        target_kind=report.target_kind,
        target_printer_id=report.target_printer_id,
        target_printer_name=report.target_printer_name,
        target_model_class=report.target_model_class,
        issues=[
            EligibilityIssueResponse(
                kind=issue.kind,
                slot_index=issue.slot_index,
                expected=issue.expected,
                actual=issue.actual,
            )
            for issue in report.issues
        ],
        printer_reports=[
            PerPrinterReportResponse(
                printer_id=r.printer_id,
                printer_name=r.printer_name,
                ok=r.ok,
                issues=[
                    EligibilityIssueResponse(
                        kind=i.kind,
                        slot_index=i.slot_index,
                        expected=i.expected,
                        actual=i.actual,
                    )
                    for i in r.issues
                ],
            )
            for r in report.printer_reports
        ],
    )


async def _load_pipeline(db: AsyncSession, pipeline_id: int) -> SlicerPipeline:
    pipeline = (
        await db.execute(
            select(SlicerPipeline).where(
                SlicerPipeline.id == pipeline_id,
                SlicerPipeline.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if pipeline is None:
        raise HTTPException(404, "Pipeline not found")
    return pipeline


async def _load_printer_status(printer_id: int | None) -> dict | None:
    """Snapshot the printer_manager's live PrinterState for the eligibility
    matcher. Returns ``None`` when the printer has no MQTT client."""
    if printer_id is None:
        return None
    from backend.app.services.printer_manager import printer_manager

    state = printer_manager.get_status(printer_id)
    if state is None:
        return None
    return {"connected": state.connected, "raw_data": state.raw_data}


def _make_status_lookup():
    """Closure that snapshots the printer_manager once per printer_id call.
    Passed to the matcher's class-targeting branch so it can read live state
    for every candidate printer."""

    def _lookup(printer_id: int) -> dict | None:
        from backend.app.services.printer_manager import printer_manager

        state = printer_manager.get_status(printer_id)
        if state is None:
            return None
        return {"connected": state.connected, "raw_data": state.raw_data}

    return _lookup


def _slice_request_from_pipeline(pipeline: SlicerPipeline) -> SliceRequest:
    try:
        raw_filaments = json.loads(pipeline.filament_presets_json or "[]")
    except (json.JSONDecodeError, TypeError):
        raw_filaments = []
    filament_presets = [
        PresetRef(source=r["source"], id=r["id"])
        for r in raw_filaments
        if isinstance(r, dict) and "source" in r and "id" in r
    ]
    try:
        bed_type = checked_bed_type(pipeline.bed_type)
    except ValueError as exc:
        raise HTTPException(400, f"{exc}. Edit the pipeline to select a supported build plate.") from exc
    return SliceRequest(
        printer_preset=PresetRef(source=pipeline.printer_preset_source, id=pipeline.printer_preset_id),
        process_preset=PresetRef(source=pipeline.process_preset_source, id=pipeline.process_preset_id),
        filament_presets=filament_presets,
        bed_type=bed_type,
        export_3mf=True,
    )


def _compute_job_status(job: PipelineJob, queue_entry: PrintQueueItem | None) -> str:
    if job.status in ("failed", "cancelled", "completed"):
        return job.status
    if queue_entry is None:
        # The foreign key is cleared when the queue row is deleted.
        return "cancelled" if job.dispatched_at is not None or job.queue_entry_id is not None else job.status
    qs = queue_entry.status
    if qs == "completed":
        return "completed"
    if qs in ("failed", "aborted"):
        return "failed"
    if qs == "cancelled":
        return "cancelled"
    if qs == "printing":
        return "printing"
    return "queued"


def _roll_up_run_status(
    persisted: str,
    job_statuses: list[str],
) -> str:
    """Compute the run-level status from the per-job statuses.

    Terminal-persisted always wins for explicit cancels / hard failures so
    the dashboard doesn't flicker when one job's queue entry hasn't caught
    up. Otherwise:
      - all completed → completed
      - any in_progress / printing / queued / dispatching → in_progress
      - any failed alongside any completed → partial_failure
      - all failed/cancelled → failed
    """
    if persisted in ("cancelled",):
        return persisted
    if not job_statuses:
        return persisted

    completed = sum(1 for s in job_statuses if s == "completed")
    failed = sum(1 for s in job_statuses if s == "failed")
    cancelled = sum(1 for s in job_statuses if s == "cancelled")
    in_flight = sum(1 for s in job_statuses if s in ("printing", "queued", "awaiting_printer", "pending"))
    total = len(job_statuses)

    if completed == total:
        return "completed"
    if in_flight > 0:
        return "in_progress" if persisted not in ("queued", "slicing", "dispatching") else persisted
    # All copies are in terminal states.
    if failed == 0 and cancelled == total:
        return "cancelled"
    if completed > 0 and (failed > 0 or cancelled > 0):
        return "partial_failure"
    if failed > 0:
        return "failed"
    return persisted


async def _materialise_run(db: AsyncSession, run: PipelineRun, visibility: RowVisibility) -> PipelineRunResponse:
    pipeline_name: str | None = None
    target_kind = None
    target_printer_id = None
    target_model_class = None
    fanout_strategy = None
    if run.pipeline_id:
        pipeline = (
            await db.execute(select(SlicerPipeline).where(SlicerPipeline.id == run.pipeline_id))
        ).scalar_one_or_none()
        if pipeline:
            pipeline_name = pipeline.name
            target_kind = pipeline.target_kind  # type: ignore[assignment]
            if pipeline.target_printer_id is not None and visibility.allows_printer(pipeline.target_printer_id):
                target_printer_id = pipeline.target_printer_id
            target_model_class = pipeline.target_model_class
            fanout_strategy = pipeline.fanout_strategy  # type: ignore[assignment]

    source_filename = None
    source_library_file_id = None
    source_archive_id = None
    library_ids = [
        file_id for file_id in (run.source_library_file_id, run.sliced_library_file_id) if file_id is not None
    ]
    library_names = (
        dict(
            (
                await db.execute(
                    select(LibraryFile.id, LibraryFile.filename).where(
                        LibraryFile.id.in_(library_ids),
                        LibraryFile.deleted_at.is_(None),
                        *library_read_criteria(visibility),
                    )
                )
            ).all()
        )
        if library_ids
        else {}
    )
    if run.source_library_file_id in library_names:
        source_library_file_id = run.source_library_file_id
        source_filename = library_names[source_library_file_id]
    elif run.source_archive_id:
        arc = await db.scalar(
            select(PrintArchive).where(PrintArchive.id == run.source_archive_id, *archive_read_criteria(visibility))
        )
        if arc is not None:
            source_archive_id = arc.id
            source_filename = arc.print_name or arc.filename

    job_rows = (
        (
            await db.execute(
                select(PipelineJob).where(PipelineJob.pipeline_run_id == run.id).order_by(PipelineJob.copy_index)
            )
        )
        .scalars()
        .all()
    )

    queue_ids = [job.queue_entry_id for job in job_rows if job.queue_entry_id is not None]
    queue_entries = {}
    visible_queue_ids = set()
    if queue_ids:
        queue_entries = {
            entry.id: entry
            for entry in await db.scalars(select(PrintQueueItem).where(PrintQueueItem.id.in_(queue_ids)))
        }
        queue_scope = visibility.criteria(
            PrintQueueItem.created_by_id,
            Permission.QUEUE_READ_ALL,
            Permission.QUEUE_READ_OWN,
            PrintQueueItem.printer_id,
        )
        visible_queue_ids = set(
            await db.scalars(select(PrintQueueItem.id).where(PrintQueueItem.id.in_(queue_ids), *queue_scope))
        )
    job_responses: list[PipelineJobResponse] = []
    job_live_statuses: list[str] = []
    for job in job_rows:
        queue_entry = queue_entries.get(job.queue_entry_id)

        printer_name: str | None = None
        assigned_printer_id = job.assigned_printer_id
        if assigned_printer_id is not None:
            if visibility.allows_printer(assigned_printer_id):
                printer_name = await db.scalar(select(Printer.name).where(Printer.id == assigned_printer_id))
            else:
                assigned_printer_id = None

        live_job_status = _compute_job_status(job, queue_entry)
        job_live_statuses.append(live_job_status)
        job_responses.append(
            PipelineJobResponse(
                id=job.id,
                pipeline_run_id=job.pipeline_run_id,
                copy_index=job.copy_index,
                assigned_printer_id=assigned_printer_id,
                assigned_printer_name=printer_name,
                queue_entry_id=job.queue_entry_id if job.queue_entry_id in visible_queue_ids else None,
                status=live_job_status,  # type: ignore[arg-type]
                error_message=job.error_message,
                dispatched_at=job.dispatched_at,
                completed_at=job.completed_at,
            )
        )

    rolled_up = _roll_up_run_status(run.status, job_live_statuses)

    return PipelineRunResponse(
        id=run.id,
        pipeline_id=run.pipeline_id,
        pipeline_name=pipeline_name,
        source_library_file_id=source_library_file_id,
        source_archive_id=source_archive_id,
        source_filename=source_filename,
        parent_run_id=run.parent_run_id,
        copies=run.copies,
        copies_completed=sum(1 for s in job_live_statuses if s == "completed"),
        copies_failed=sum(1 for s in job_live_statuses if s == "failed"),
        copies_cancelled=sum(1 for s in job_live_statuses if s == "cancelled"),
        copies_in_progress=sum(
            1 for s in job_live_statuses if s in ("printing", "queued", "awaiting_printer", "pending")
        ),
        status=rolled_up,  # type: ignore[arg-type]
        slice_job_id=run.slice_job_id,
        sliced_library_file_id=run.sliced_library_file_id if run.sliced_library_file_id in library_names else None,
        eligibility_overridden=run.eligibility_overridden,
        error_message=run.error_message,
        created_by=run.created_by,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        jobs=job_responses,
        target_kind=target_kind,
        target_printer_id=target_printer_id,
        target_model_class=target_model_class,
        fanout_strategy=fanout_strategy,
    )


async def _publish_run_event(db: AsyncSession, run: PipelineRun) -> None:
    """Broadcast a ``pipeline_run_updated`` event with the full materialised
    run, with a global fallback for installations with authentication disabled."""
    try:
        owner_id = await db.scalar(select(PipelineRun.created_by).where(PipelineRun.id == run.id))
        if owner_id is None and await is_auth_enabled(db):
            return
        owner = await db.get(User, owner_id, populate_existing=True) if owner_id is not None else None
        if owner_id is not None and (owner is None or not owner.is_active):
            return
        visibility = await resolve_row_visibility(db, owner, None)
        payload = await _materialise_run(db, run, visibility)
        await ws_manager.broadcast_to_user(
            owner_id,
            {
                "type": "pipeline_run_updated",
                "run": payload.model_dump(mode="json"),
            },
            user_sessions_only=True,
        )
    except Exception:
        logger.exception("Failed to broadcast pipeline_run_updated for run %d", run.id)


# Source resolution + orchestration


SourceKind = Literal["library_file", "archive"]


async def _resolve_source(
    db: AsyncSession,
    *,
    library_file_id: int | None,
    archive_id: int | None,
    visibility: RowVisibility,
) -> tuple[SourceKind, int, str, Path]:
    if library_file_id is not None:
        lib = await require_library_source(db, library_file_id, visibility)
        src_path = (
            Path(app_settings.base_dir) / lib.file_path
        )  # SEC-PATH-OK: lib.file_path is a LibraryFile DB column set only by the upload route, which writes a UUID-named file under base_dir/library_files/.
        if not src_path.exists():
            raise HTTPException(404, "Source library file missing on disk")
        return ("library_file", lib.id, lib.filename, src_path)

    assert archive_id is not None
    arc = await require_archive_source(db, archive_id, visibility)
    rel = arc.source_3mf_path or arc.file_path
    if not rel:
        raise HTTPException(400, "Archive has no source file to slice")
    src_path = (
        Path(app_settings.base_dir) / rel
    )  # SEC-PATH-OK: rel is archive.source_3mf_path / archive.file_path, both set by upload-time validators that already do resolve+relative_to containment.
    if not src_path.exists():
        raise HTTPException(404, "Archive source file missing on disk")
    name = arc.filename or arc.print_name or src_path.name
    return ("archive", arc.id, name, src_path)


async def _pick_assignments(
    db: AsyncSession,
    pipeline: SlicerPipeline,
    copies: int,
    printer_ids: set[int] | None = None,
    *,
    allow_model_target: bool = True,
) -> list[tuple[int | None, str | None]]:
    """Return ``[(printer_id_or_None, target_model_or_None), ...]`` of length
    ``copies`` per the pipeline's fanout strategy. ``target_model_class``
    items leave ``printer_id`` None so the scheduler picks any free matching
    printer; specific assignments fill ``printer_id``."""
    target_kind = pipeline.target_kind or "specific_printer"
    if target_kind == "specific_printer" or pipeline.target_printer_id is not None:
        assert pipeline.target_printer_id is not None
        if printer_ids is not None and pipeline.target_printer_id not in printer_ids:
            raise HTTPException(404, "Printer not found")
        return [(pipeline.target_printer_id, None)] * copies

    if not allow_model_target:
        raise HTTPException(403, "This API key must target a specific printer")

    # Class-targeting. Enumerate matching printers + apply the strategy.
    query = select(Printer).where(
        func.lower(Printer.model) == (pipeline.target_model_class or "").lower(), Printer.is_active.is_(True)
    )
    if printer_ids is not None:
        query = query.where(Printer.id.in_(printer_ids))
    matching = (await db.scalars(query.order_by(Printer.id))).all()
    if not matching:
        # Shouldn't reach here when eligibility passes, but failing gracefully
        # is better than a TypeError on next-slot pick.
        return [(None, pipeline.target_model_class)] * copies

    strategy = pipeline.fanout_strategy or "max_parallel"
    if strategy == "fill_one_first":
        # Pin every copy to the first match. Scheduler dispatches them serially
        # to that printer. If the printer breaks, copies wait; that's the
        # documented trade-off.
        return [(matching[0].id, None)] * copies
    if strategy == "round_robin":
        # Cycle through eligible printers — copy ``i`` lands on
        # ``matching[i % len(matching)]``. Each item gets a fixed printer_id.
        return [(matching[i % len(matching)].id, None) for i in range(copies)]
    # max_parallel — leave printer_id=None, set target_model so the scheduler
    # picks any free X1C / P1S / … for each item independently.
    return [(None, matching[0].model)] * copies


def _make_orchestration_callable(
    *,
    run_id: int,
    pipeline_id: int,
    src_kind: SourceKind,
    src_id: int,
    src_filename: str,
    src_path: Path,
    creator_user_id: int | None,
    copies: int,
    creator_restricted: bool = False,
    printer_ids: set[int] | None = None,
    allow_model_target: bool = True,
):
    """Returns the async callable that ``slice_dispatch.enqueue`` runs as the
    background slice job. Wraps slice + multi-copy enqueue + state update."""

    async def _orchestrate(slice_job_id: int) -> dict:
        from backend.app.api.routes.library import slice_and_persist

        async with async_session() as session:
            run = (await session.execute(select(PipelineRun).where(PipelineRun.id == run_id))).scalar_one_or_none()
            pipeline = (
                await session.execute(select(SlicerPipeline).where(SlicerPipeline.id == pipeline_id))
            ).scalar_one_or_none()
            if run is None or pipeline is None:
                logger.warning("pipeline_run %d or pipeline %d disappeared mid-orchestration", run_id, pipeline_id)
                return {}

            # Honour a cancel that landed between ``POST /run`` returning and
            # this background task starting. If the run was cancelled while
            # still in ``queued`` we must NOT flip it back to ``slicing`` —
            # the operator's intent was to stop, and overwriting status here
            # was the bug that left runs stuck at ``dispatching`` after a
            # user-side cancel (#1425 PR C bug report).
            if run.status == "cancelled":
                logger.info("pipeline_run %d was cancelled before slicing started", run_id)
                return {}

            run.status = "slicing"
            run.started_at = datetime.now(timezone.utc)
            await session.commit()
            await _publish_run_event(session, run)

            folder_id: int | None = None
            if src_kind == "library_file":
                lib = (await session.execute(select(LibraryFile).where(LibraryFile.id == src_id))).scalar_one_or_none()
                if lib is not None:
                    folder_id = lib.folder_id

            try:
                slice_request = _slice_request_from_pipeline(pipeline)
                printer_ref = slice_request.printer_preset
                process_ref = slice_request.process_preset
                filament_refs = slice_request.filament_presets
                if any(
                    ref is not None and ref.source == "standard" for ref in [printer_ref, process_ref, *filament_refs]
                ):
                    cloud_user = await session.get(User, creator_user_id) if creator_user_id is not None else None
                    aliases = await load_stock_aliases(session, cloud_user)
                    if printer_ref is not None:
                        slice_request.printer_preset = listed_stock_ref(aliases, "printer", printer_ref)
                    if process_ref is not None:
                        slice_request.process_preset = listed_stock_ref(aliases, "process", process_ref)
                    slice_request.filament_presets = [
                        listed_stock_ref(aliases, "filament", ref) for ref in filament_refs
                    ]
                slice_response = await slice_and_persist(
                    session,
                    model_bytes=src_path.read_bytes(),
                    model_filename=src_filename,
                    folder_id=folder_id,
                    extra_metadata={
                        f"sliced_from_{src_kind}_id": src_id,
                        "sliced_via_pipeline_id": pipeline.id,
                        "sliced_via_pipeline_run_id": run.id,
                    },
                    request=slice_request,
                    current_user_id=creator_user_id,
                    job_id=slice_job_id,
                )
            except HTTPException as exc:
                run.status = "failed"
                run.error_message = f"Slice failed: {exc.detail}"
                run.completed_at = datetime.now(timezone.utc)
                await session.commit()
                await _publish_run_event(session, run)
                raise
            except Exception as exc:
                logger.exception("Pipeline run %d slice raised unexpectedly", run_id)
                run.status = "failed"
                run.error_message = f"Slice failed: {exc}"
                run.completed_at = datetime.now(timezone.utc)
                await session.commit()
                await _publish_run_event(session, run)
                raise

            run.sliced_library_file_id = slice_response.library_file_id

            # Re-check cancellation: the slice can take minutes, and the
            # operator may have hit Cancel during that window. Refresh from
            # the DB rather than trusting our in-memory `run` (the cancel
            # route writes via a separate session). When cancelled, don't
            # enqueue print queue items — that's the whole point of cancel.
            await session.refresh(run)
            if run.status == "cancelled":
                logger.info("pipeline_run %d cancelled mid-slice; skipping queue enqueue", run_id)
                await session.commit()
                return slice_response.model_dump()

            # PR C: enqueue N copies per the picked assignment strategy.
            from backend.app.services.queue_filament_mapping import creator_printer_ids

            allowed = printer_ids
            if run.created_by is not None:
                current_scope = await creator_printer_ids(session, run.created_by)
                if current_scope is not None:
                    allowed = current_scope if allowed is None else allowed & current_scope
            try:
                assignments = await _pick_assignments(
                    session, pipeline, copies, allowed, allow_model_target=allow_model_target
                )
            except HTTPException as exc:
                run.status = "failed"
                run.error_message = str(exc.detail)
                run.completed_at = datetime.now(timezone.utc)
                await session.commit()
                await _publish_run_event(session, run)
                raise

            jobs = (
                (
                    await session.execute(
                        select(PipelineJob)
                        .where(PipelineJob.pipeline_run_id == run_id)
                        .order_by(PipelineJob.copy_index)
                    )
                )
                .scalars()
                .all()
            )
            if len(jobs) != copies:
                logger.warning("pipeline_run %d expected %d jobs, found %d", run_id, copies, len(jobs))

            from backend.app.services.print_account_ownership import existing_print_owner_id

            owner_id = await existing_print_owner_id(session, run.created_by)
            hold_ownerless_copies = owner_id is None and creator_restricted and pipeline.target_printer_id is None
            print_options = await default_print_options(session)
            for job, (printer_id, target_model) in zip(jobs, assignments, strict=False):
                queue_item = PrintQueueItem(
                    printer_id=printer_id,
                    target_model=target_model,
                    library_file_id=slice_response.library_file_id,
                    created_by_id=owner_id,
                    status="pending",
                    manual_start=hold_ownerless_copies,
                    **print_options,
                )
                session.add(queue_item)
                await session.flush()

                job.queue_entry_id = queue_item.id
                job.assigned_printer_id = printer_id  # may be None for max_parallel
                # Don't write job.status yet — final cancellation check below
                # may flip it to 'cancelled' instead. dispatched_at is fine to
                # set unconditionally since the orchestration actually got here.
                job.dispatched_at = datetime.now(timezone.utc)

            # Final cancellation check before committing 'dispatching'. The
            # cancel route writes via a separate session so we have to refresh
            # to see the latest. If the cancel landed in this narrow window —
            # AFTER the post-slice refresh but BEFORE this commit — the queue
            # entries we just created would otherwise pick up and print. Mark
            # them + the per-copy jobs cancelled so the user's intent sticks.
            await session.refresh(run)
            if run.status == "cancelled":
                logger.info(
                    "pipeline_run %d cancelled in the dispatch window; cancelling its %d queue entries",
                    run_id,
                    len(jobs),
                )
                for job in jobs:
                    if job.queue_entry_id:
                        qe = (
                            await session.execute(select(PrintQueueItem).where(PrintQueueItem.id == job.queue_entry_id))
                        ).scalar_one_or_none()
                        if qe is not None and qe.status in ("pending", "queued"):
                            qe.status = "cancelled"
                            qe.completed_at = datetime.now(timezone.utc)
                    if job.status not in ("completed", "failed", "cancelled"):
                        job.status = "cancelled"
                        job.completed_at = datetime.now(timezone.utc)
                await session.commit()
                await _publish_run_event(session, run)
                return slice_response.model_dump()

            for job in jobs:
                job.status = "queued"
            run.status = "dispatching"
            await session.commit()
            await announce_queue_jobs_added(
                [job.queue_entry_id for job in jobs if job.queue_entry_id], session_factory=async_session
            )
            await _publish_run_event(session, run)

            return slice_response.model_dump()

    return _orchestrate


# /slicer-pipelines/{id}/check-eligibility


@pipeline_run_create_router.post("/{pipeline_id}/check-eligibility", response_model=EligibilityReportResponse)
async def check_eligibility(
    pipeline_id: int,
    body: CheckEligibilityRequest,
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PIPELINES_READ),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
    db: AsyncSession = DB_SESSION,
):
    pipeline = await _load_pipeline(db, pipeline_id)
    visibility = await resolve_row_visibility(db, current_user, api_key)
    _check_pipeline_target(pipeline, visibility)
    await _resolve_source(
        db,
        library_file_id=body.source_library_file_id,
        archive_id=body.source_archive_id,
        visibility=visibility,
    )
    if pipeline.target_kind == "printer_class" and pipeline.target_printer_id is None:
        report = await check_pipeline_eligibility(
            db, pipeline, status_lookup=_make_status_lookup(), printer_ids=visibility.printer_ids
        )
    else:
        status = await _load_printer_status(pipeline.target_printer_id)
        report = await check_pipeline_eligibility(db, pipeline, status)
    return _serialise_status(report)


# /slicer-pipelines/{id}/run


@pipeline_run_create_router.post("/{pipeline_id}/run", response_model=PipelineRunResponse, status_code=202)
async def run_pipeline(
    pipeline_id: int,
    body: PipelineRunCreateRequest,
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PIPELINES_RUN),
    api_key_cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
    db: AsyncSession = DB_SESSION,
):
    from backend.app.api.routes.settings import get_setting
    from backend.app.services.slice_dispatch import slice_dispatch

    pipeline = await _load_pipeline(db, pipeline_id)
    visibility = await resolve_row_visibility(db, current_user, api_key)
    _check_pipeline_target(pipeline, visibility)
    owner = visibility.user
    src_kind, src_id, src_filename, src_path = await _resolve_source(
        db,
        library_file_id=body.source_library_file_id,
        archive_id=body.source_archive_id,
        visibility=visibility,
    )
    cloud_user = current_user or api_key_cloud_owner

    # The sidecar cannot import STEP/STP, so refuse the run up front instead
    # of failing mid-pipeline (#92). Sources without a recognisable extension
    # (archives named after their print_name) stay allowed, as before.
    if is_unsliceable_cad_filename(src_filename):
        raise HTTPException(400, unsliceable_detail(src_filename))

    # Cap copies against the configured ceiling.
    raw_cap = await get_setting(db, "pipeline_max_copies")
    try:
        cap = int(raw_cap) if raw_cap else 50
    except (TypeError, ValueError):
        cap = 50
    if body.copies > cap:
        raise HTTPException(
            422,
            f"copies={body.copies} exceeds pipeline_max_copies setting ({cap})",
        )

    # Eligibility pre-flight.
    if pipeline.target_kind == "printer_class" and pipeline.target_printer_id is None:
        report = await check_pipeline_eligibility(
            db, pipeline, status_lookup=_make_status_lookup(), printer_ids=visibility.printer_ids
        )
    else:
        status = await _load_printer_status(pipeline.target_printer_id)
        report = await check_pipeline_eligibility(db, pipeline, status)

    if not report.ok and not body.force:
        raise HTTPException(status_code=409, detail=_serialise_status(report).model_dump())

    # Need a target — specific or class — to dispatch.
    if pipeline.target_printer_id is None and not pipeline.target_model_class:
        raise HTTPException(
            400,
            "Pipeline has no target. Open the pipeline in Settings → Workflow → Pipelines and choose a target printer or printer class.",
        )

    run = PipelineRun(
        pipeline_id=pipeline.id,
        source_library_file_id=src_id if src_kind == "library_file" else None,
        source_archive_id=src_id if src_kind == "archive" else None,
        copies=body.copies,
        status="queued",
        eligibility_overridden=(not report.ok and body.force),
        created_by=owner.id if owner else None,
    )
    db.add(run)
    await db.flush()

    # One PipelineJob per copy. PR B was copies=1, PR C generalises.
    for i in range(body.copies):
        db.add(
            PipelineJob(
                pipeline_run_id=run.id,
                copy_index=i,
                status="pending",
            )
        )
    await db.commit()
    await db.refresh(run)
    await _publish_run_event(db, run)

    orchestrate = _make_orchestration_callable(
        run_id=run.id,
        pipeline_id=pipeline.id,
        src_kind=src_kind,
        src_id=src_id,
        src_filename=src_filename,
        src_path=src_path,
        creator_user_id=cloud_user.id if cloud_user else None,
        copies=body.copies,
        creator_restricted=visibility.printer_ids is not None,
        printer_ids=visibility.printer_ids,
        allow_model_target=visibility.can_use_model_target,
    )
    slice_job = await slice_dispatch.enqueue(
        kind="library_file" if src_kind == "library_file" else "archive",
        source_id=src_id,
        source_name=src_filename,
        owner_id=run.created_by,
        run=orchestrate,
    )

    run.slice_job_id = slice_job.id
    await db.commit()
    await db.refresh(run)

    return await _materialise_run(db, run, visibility)


# Lists, reads, cancel, retry-failed


@pipeline_run_create_router.get("/{pipeline_id}/runs", response_model=PipelineRunListResponse)
async def list_runs_for_pipeline(
    pipeline_id: int,
    limit: int = 10,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.PIPELINES_READ),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
    db: AsyncSession = DB_SESSION,
):
    visibility = await resolve_row_visibility(db, user, api_key)
    limit = max(1, min(limit, 100))
    rows = (
        (
            await db.execute(
                select(PipelineRun)
                .where(PipelineRun.pipeline_id == pipeline_id)
                .order_by(PipelineRun.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    total = (
        await db.execute(select(func.count()).select_from(PipelineRun).where(PipelineRun.pipeline_id == pipeline_id))
    ).scalar() or 0
    return PipelineRunListResponse(
        runs=[await _materialise_run(db, r, visibility) for r in rows],
        total=total,
    )


@pipeline_run_router.get("", response_model=PipelineRunListResponse)
async def list_all_runs(
    limit: int = 25,
    offset: int = 0,
    pipeline_id: int | None = None,
    status: str | None = None,
    target_printer_id: int | None = None,
    target_model_class: str | None = None,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.PIPELINES_READ),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
    db: AsyncSession = DB_SESSION,
):
    """Dashboard list. Newest first; filters on pipeline_id + status +
    target_printer_id + target_model_class. The ``status`` filter matches
    the persisted snapshot, not the live roll-up — in-progress runs may
    appear under ``dispatching`` until the next state transition writes
    through. ``target_*`` filters JOIN to the pipeline so runs whose
    pipeline currently points at the printer / class are returned."""
    visibility = await resolve_row_visibility(db, user, api_key)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    stmt = select(PipelineRun)
    count_stmt = select(func.count()).select_from(PipelineRun)
    if pipeline_id is not None:
        stmt = stmt.where(PipelineRun.pipeline_id == pipeline_id)
        count_stmt = count_stmt.where(PipelineRun.pipeline_id == pipeline_id)
    if status:
        stmt = stmt.where(PipelineRun.status == status)
        count_stmt = count_stmt.where(PipelineRun.status == status)
    if target_printer_id is not None or target_model_class is not None:
        stmt = stmt.join(SlicerPipeline, SlicerPipeline.id == PipelineRun.pipeline_id)
        count_stmt = count_stmt.join(SlicerPipeline, SlicerPipeline.id == PipelineRun.pipeline_id)
        if target_printer_id is not None:
            stmt = stmt.where(SlicerPipeline.target_printer_id == target_printer_id)
            count_stmt = count_stmt.where(SlicerPipeline.target_printer_id == target_printer_id)
        if target_model_class is not None:
            stmt = stmt.where(SlicerPipeline.target_model_class == target_model_class)
            count_stmt = count_stmt.where(SlicerPipeline.target_model_class == target_model_class)

    rows = (await db.execute(stmt.order_by(desc(PipelineRun.id)).offset(offset).limit(limit))).scalars().all()
    total = (await db.execute(count_stmt)).scalar() or 0

    return PipelineRunListResponse(
        runs=[await _materialise_run(db, r, visibility) for r in rows],
        total=total,
    )


_TERMINAL_RUN_STATUSES = ("completed", "failed", "cancelled", "partial_failure")


@pipeline_run_router.post("/clear")
async def clear_terminal_runs(
    user: User | None = RequirePermissionIfAuthEnabled(Permission.PIPELINES_WRITE),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
    db: AsyncSession = DB_SESSION,
):
    """Delete every terminal pipeline run (completed / failed / cancelled /
    partial_failure). In-flight runs (queued / slicing / dispatching /
    in_progress) are preserved — clearing those mid-flight would lose the
    operator's intent. Cascades to PipelineJob via the ondelete='CASCADE'
    relationship; the linked PrintQueueItem rows stay (they have their own
    lifecycle on the queue page)."""
    visibility = await resolve_row_visibility(db, user, api_key)
    # Count first so the response can report how many got cleared. Done
    # under the same session/transaction as the delete so the numbers can't
    # drift if another caller races in.
    scope = visibility.criteria(PipelineRun.created_by, Permission.QUEUE_UPDATE_ALL, Permission.QUEUE_UPDATE_OWN)
    conditions = (PipelineRun.status.in_(_TERMINAL_RUN_STATUSES), *scope)
    count_stmt = select(func.count()).select_from(PipelineRun).where(*conditions)
    n = (await db.execute(count_stmt)).scalar() or 0
    if n > 0:
        run_ids = select(PipelineRun.id).where(*conditions)
        await db.execute(delete(PipelineJob).where(PipelineJob.pipeline_run_id.in_(run_ids)))
        await db.execute(delete(PipelineRun).where(*conditions))
        await db.commit()
    return {"deleted": n}


@pipeline_run_router.get("/{run_id}", response_model=PipelineRunResponse)
async def get_run(
    run_id: int,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.PIPELINES_READ),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
    db: AsyncSession = DB_SESSION,
):
    visibility = await resolve_row_visibility(db, user, api_key)
    run = (await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Pipeline run not found")
    return await _materialise_run(db, run, visibility)


@pipeline_run_router.post("/{run_id}/cancel", response_model=PipelineRunResponse)
async def cancel_run(
    run_id: int,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.PIPELINES_RUN),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
    db: AsyncSession = DB_SESSION,
):
    """Cancel a queued / in-flight run. Cascades to all non-terminal queue
    entries; in-flight prints continue on the printer (operator must Stop)."""
    visibility = await resolve_row_visibility(db, user, api_key)
    run = (await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Pipeline run not found")
    await _check_run_api_key_printer_access(db, run, api_key)
    scope = visibility.criteria(PipelineRun.created_by, Permission.QUEUE_UPDATE_ALL, Permission.QUEUE_UPDATE_OWN)
    if await db.scalar(select(PipelineRun.id).where(PipelineRun.id == run_id, *scope)) is None:
        raise HTTPException(403, "The caller cannot cancel this pipeline run")

    if run.status in ("completed", "failed", "cancelled", "partial_failure"):
        return await _materialise_run(db, run, visibility)

    run.status = "cancelled"
    run.completed_at = datetime.now(timezone.utc)
    if not run.error_message:
        run.error_message = "Cancelled by user"

    job_rows = (await db.execute(select(PipelineJob).where(PipelineJob.pipeline_run_id == run.id))).scalars().all()
    cancelled_entries = []
    for job in job_rows:
        if job.queue_entry_id:
            queue_entry = (
                await db.execute(select(PrintQueueItem).where(PrintQueueItem.id == job.queue_entry_id))
            ).scalar_one_or_none()
            if queue_entry is not None and queue_entry.status in ("pending", "queued"):
                queue_entry.status = "cancelled"
                queue_entry.completed_at = datetime.now(timezone.utc)
                cancelled_entries.append(queue_entry.id)
        if job.status not in ("completed", "failed", "cancelled"):
            job.status = "cancelled"
            job.completed_at = datetime.now(timezone.utc)

    await db.commit()
    from backend.app.services.print_scheduler import scheduler

    for entry_id in cancelled_entries:
        scheduler.notify_dispatch_cancelled(entry_id)
    await db.refresh(run)
    await _publish_run_event(db, run)
    return await _materialise_run(db, run, visibility)


@pipeline_run_router.post("/{run_id}/retry-failed", response_model=PipelineRunResponse, status_code=202)
async def retry_failed(
    run_id: int,
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PIPELINES_RUN),
    api_key_cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
    db: AsyncSession = DB_SESSION,
):
    """Create a new run with copies = (failed + cancelled count) from the
    parent. Same pipeline, same source. Eligibility re-checked at run time
    (it might pass this time — operator may have fixed the issue)."""
    parent = (await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))).scalar_one_or_none()
    if parent is None:
        raise HTTPException(404, "Pipeline run not found")
    if parent.pipeline_id is None:
        raise HTTPException(400, "Original pipeline was deleted; cannot retry")
    if parent.source_library_file_id is None and parent.source_archive_id is None:
        raise HTTPException(400, "Original source was deleted; cannot retry")

    # Count the parent's failed + cancelled jobs.
    parent_jobs = (
        (await db.execute(select(PipelineJob).where(PipelineJob.pipeline_run_id == parent.id))).scalars().all()
    )
    fail_count = 0
    for j in parent_jobs:
        queue_entry = None
        if j.queue_entry_id:
            queue_entry = (
                await db.execute(select(PrintQueueItem).where(PrintQueueItem.id == j.queue_entry_id))
            ).scalar_one_or_none()
        live = _compute_job_status(j, queue_entry)
        if live in ("failed", "cancelled"):
            fail_count += 1

    if fail_count == 0:
        raise HTTPException(400, "No failed copies to retry")

    # Build the request payload the same way the user would have via /run.
    body = PipelineRunCreateRequest(
        source_library_file_id=parent.source_library_file_id,
        source_archive_id=parent.source_archive_id,
        copies=fail_count,
        force=True,  # operator already accepted eligibility on the parent
    )

    # Reuse the run_pipeline route logic via a direct call — keeps the
    # orchestration single-sourced. The result inherits parent_run_id.
    new_run_response = await run_pipeline(
        parent.pipeline_id,
        body,
        current_user=current_user,
        api_key_cloud_owner=api_key_cloud_owner,
        api_key=api_key,
        db=db,
    )

    # Stamp parent_run_id on the freshly-created run.
    new_row = (await db.execute(select(PipelineRun).where(PipelineRun.id == new_run_response.id))).scalar_one_or_none()
    if new_row is not None:
        new_row.parent_run_id = parent.id
        await db.commit()
        await db.refresh(new_row)
        visibility = await resolve_row_visibility(db, current_user, api_key)
        return await _materialise_run(db, new_row, visibility)
    return new_run_response
