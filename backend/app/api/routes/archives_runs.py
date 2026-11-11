"""Archive run aggregation, response assembly, and outcome confirmation."""

from fastapi import HTTPException, Request
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import OwnershipAccess
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
from backend.app.schemas.archive import OutcomeConfirmation
from backend.app.services.archive_plate_estimates import estimate_for_plate
from backend.app.services.archive_scope import whole_archive_conditions
from backend.app.services.print_log_run import run_visibility_conditions


def compute_time_accuracy(archive: PrintArchive, run_aggregate: dict | None = None) -> dict:
    """Compare the latest completed print with the estimate of its own plate."""
    runs = run_aggregate or {}
    if runs.get("scoped") or "selected_run" in runs:
        latest = runs.get("selected_run", runs.get("latest_visible"))
        if latest is None:
            return {"actual_time_seconds": None, "time_accuracy": None, "time_estimate_seconds": None}
    else:
        latest = runs.get("latest_finished") if archive.status != RUN_OPEN else None
    plates = getattr(archive, "plate_estimates", None)
    plate_id = latest.plate_id if latest is not None else getattr(archive, "plate_id", None)
    estimate, _ = estimate_for_plate(plates, plate_id, archive.print_time_seconds)
    result = {"actual_time_seconds": None, "time_accuracy": None, "time_estimate_seconds": estimate}
    if not plates and (runs.get("run_count") or 0) > 1:
        return result
    source = latest if latest is not None else archive
    unmeasured = latest.duration_unmeasured if latest is not None else runs.get("unmeasured_run_count")
    if source.status == "completed" and not unmeasured:
        actual = latest.duration_seconds if latest is not None else None
        if not actual and source.started_at and source.completed_at:
            actual = int((source.completed_at - source.started_at).total_seconds())
        if actual and actual > 0:
            result["actual_time_seconds"] = actual
            if estimate and 5 <= (accuracy := 100 * estimate / actual) <= 500:
                result["time_accuracy"] = round(accuracy, 1)
    return result


async def _load_run_aggregates(
    db: AsyncSession, archive_ids: list[int], access: OwnershipAccess | None = None
) -> dict[int, dict]:
    """Batch-load per-archive run aggregates from PrintLogEntry.

    Returns ``{archive_id: {run_count, last_run_at, total_filament_actual_grams,
    successful_run_count, failed_run_count}}``. Archives with no logged runs are
    absent from the map; callers should treat that as zero/none.
    """
    if not archive_ids:
        return {}
    filters = [PrintLogEntry.archive_id.in_(archive_ids)]
    if access is not None:
        filters.extend(run_visibility_conditions(access))
    rows = await db.execute(
        select(
            PrintLogEntry.archive_id,
            func.count(PrintLogEntry.id).label("run_count"),
            func.max(PrintLogEntry.started_at).label("last_run_at"),
            func.coalesce(func.sum(PrintLogEntry.filament_used_grams), 0).label("total_filament"),
            func.sum(case((PrintLogEntry.status == "completed", 1), else_=0)).label("successful"),
            func.sum(case((PrintLogEntry.status == "failed", 1), else_=0)).label("failed"),
            func.sum(case((PrintLogEntry.duration_unmeasured.is_(True), 1), else_=0)).label("unmeasured"),
        )
        .where(*filters)
        .group_by(PrintLogEntry.archive_id)
    )
    aggregates: dict[int, dict] = {}
    for archive_id, run_count, last_run_at, total_filament, successful, failed, unmeasured in rows.all():
        aggregates[archive_id] = {
            "run_count": int(run_count or 0),
            "last_run_at": last_run_at,
            "total_filament_actual_grams": float(total_filament) if total_filament else None,
            "successful_run_count": int(successful or 0),
            "failed_run_count": int(failed or 0),
            "unmeasured_run_count": int(unmeasured or 0),
        }
    from backend.app.models.print_queue import PrintQueueItem

    ranked = (
        select(
            PrintLogEntry.id,
            func.row_number()
            .over(
                partition_by=(PrintLogEntry.archive_id, PrintLogEntry.status == RUN_OPEN),
                order_by=(PrintLogEntry.started_at.desc().nulls_last(), PrintLogEntry.id.desc()),
            )
            .label("position"),
        )
        .where(*filters)
        .subquery()
    )
    current = await db.execute(
        select(PrintLogEntry, PrintQueueItem.batch_id)
        .join(ranked, ranked.c.id == PrintLogEntry.id)
        .outerjoin(PrintQueueItem, PrintLogEntry.queue_item_id == PrintQueueItem.id)
        .where(ranked.c.position == 1)
        .order_by(PrintLogEntry.started_at.desc().nulls_last(), PrintLogEntry.id.desc())
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )
    for run, batch_id in current:
        summary = aggregates.setdefault(run.archive_id, {})
        summary.setdefault("latest_visible", run)
        if run.status != RUN_OPEN:
            summary.update(
                outcome_run_id=run.id,
                outcome_expected_parts=run.quantity,
                outcome_batch_id=batch_id,
                latest_finished=run,
            )
    whole = whole_archive_conditions(access) if access is not None else ()
    if whole:
        partial = await db.scalars(select(PrintArchive.id).where(PrintArchive.id.in_(archive_ids), ~and_(*whole)))
        for archive_id in partial:
            aggregates.setdefault(archive_id, {})["scoped"] = True
    videos = await db.execute(
        select(PrintLogEntry.archive_id, PrintLogEntry.timelapse_path)
        .where(*filters, PrintLogEntry.timelapse_path.is_not(None))
        .distinct()
    )
    for archive_id, path in videos:
        aggregates.setdefault(archive_id, {}).setdefault("run_timelapses", set()).add(path)
    return aggregates


def _apply_scoped_run(data, run):
    fields = (
        "printer_id",
        "plate_id",
        "started_at",
        "completed_at",
        "failure_reason",
        "quantity",
        "confirm_requested",
        "user_verdict",
        "good_quantity",
        "reject_quantity",
        "user_verdict_source",
        "user_verdict_at",
        "energy_kwh",
        "energy_cost",
    )
    data.update({field: getattr(run, field, None) for field in fields})
    data.update(
        status=run.status if run is not None else "archived",
        quantity=run.quantity if run is not None else 1,
        confirm_requested=bool(run and run.confirm_requested),
        timelapse_path=None,
        photos=None,
        extra_data=None,
        cost=run.cost if run is not None else None,
    )
    # The storage path contains the printer that first archived the file.
    data["file_path"] = ""
    for field in ("thumbnail_path", "source_3mf_path", "f3d_path"):
        data[field] = None


def archive_to_response(
    archive: PrintArchive,
    duplicates: list[dict] | None = None,
    duplicate_count: int = 0,
    duplicate_sequence: int = 0,
    original_archive_id: int | None = None,
    run_aggregate: dict | None = None,
) -> dict:
    """Convert archive model to response dict with computed fields."""
    from backend.app.api.routes import archives

    data = {
        "id": archive.id,
        "printer_id": archive.printer_id,
        "project_id": archive.project_id,
        "project_name": archive.project.name if archive.project else None,
        "filename": archive.filename,
        "file_path": archive.file_path,
        "file_size": archive.file_size,
        "content_hash": archive.content_hash,
        "thumbnail_path": archive.thumbnail_path,
        "timelapse_path": archive.timelapse_path,
        "source_3mf_path": archive.source_3mf_path,
        "f3d_path": archive.f3d_path,
        "duplicates": duplicates,
        "duplicate_count": duplicate_count if duplicates is None else len(duplicates),
        "duplicate_sequence": duplicate_sequence,
        "original_archive_id": original_archive_id,
        "print_name": archive.print_name,
        "plate_id": archive.plate_id,
        "print_time_seconds": archive.print_time_seconds,
        "filament_used_grams": archive.filament_used_grams,
        "filament_type": archive.filament_type,
        "filament_color": archive.filament_color,
        "layer_height": archive.layer_height,
        "total_layers": archive.total_layers,
        "nozzle_diameter": archive.nozzle_diameter,
        "bed_temperature": archive.bed_temperature,
        "bed_type": archive.bed_type,
        "nozzle_temperature": archive.nozzle_temperature,
        "sliced_for_model": archive.sliced_for_model,
        "status": archive.status,
        "started_at": archive.started_at,
        "completed_at": archive.completed_at,
        "extra_data": archive.extra_data,
        "makerworld_url": archive.makerworld_url,
        "designer": archive.designer,
        "external_url": archive.external_url,
        "is_favorite": archive.is_favorite,
        "tags": archive.tags,
        "notes": archive.notes,
        "cost": archive.cost,
        "photos": archive.photos,
        "failure_reason": archive.failure_reason,
        "quantity": archive.quantity,
        "confirm_requested": bool(archive.confirm_requested),
        "user_verdict": archive.user_verdict,
        "good_quantity": archive.good_quantity,
        "reject_quantity": archive.reject_quantity,
        "user_verdict_source": archive.user_verdict_source,
        "user_verdict_at": archive.user_verdict_at,
        "energy_kwh": archive.energy_kwh,
        "energy_cost": archive.energy_cost,
        "created_at": archive.created_at,
        # User tracking (Issue #206)
        "created_by_id": archive.created_by_id,
        "created_by_username": archive.created_by.username if archive.created_by else None,
    }

    summary = run_aggregate or {}
    selected = summary.get("selected_run")
    if summary.get("scoped"):
        _apply_scoped_run(data, selected or summary.get("latest_visible"))
    elif selected is not None:
        for field in (
            "printer_id",
            "plate_id",
            "status",
            "started_at",
            "completed_at",
            "failure_reason",
            "quantity",
            "confirm_requested",
            "user_verdict",
            "good_quantity",
            "reject_quantity",
            "user_verdict_source",
            "user_verdict_at",
            "energy_kwh",
            "energy_cost",
            "photos",
            "timelapse_path",
        ):
            data[field] = getattr(selected, field)
    videos = set(summary.get("run_timelapses", ()))
    if archive.timelapse_path and not summary.get("scoped"):
        videos.add(archive.timelapse_path)
    data["timelapse_count"] = len(videos)
    if selected is not None:
        data.update(run_id=selected.id, outcome_run_id=selected.id, outcome_expected_parts=selected.quantity)

    # Compare the latest print with its selected plate.
    accuracy_data = archives.compute_time_accuracy(archive, run_aggregate)
    data.update(accuracy_data)

    if run_aggregate:
        latest = run_aggregate.get("latest_visible")
        data["latest_run_id"] = latest.id if latest is not None else None
        if selected is None:
            for field in ("outcome_run_id", "outcome_expected_parts", "outcome_batch_id"):
                data[field] = run_aggregate.get(field)
        data["run_count"] = run_aggregate.get("run_count", 0)
        data["last_run_at"] = run_aggregate.get("last_run_at")
        data["total_filament_actual_grams"] = run_aggregate.get("total_filament_actual_grams")
        data["successful_run_count"] = run_aggregate.get("successful_run_count", 0)
        data["failed_run_count"] = run_aggregate.get("failed_run_count", 0)

    return data


async def confirm_production_outcome(
    archive_id: int,
    outcome: OutcomeConfirmation,
    run_id: int | None,
    db: AsyncSession,
    auth_result: OwnershipAccess,
):
    """Inspect or correct the current run with normal ownership and printer scopes."""
    from backend.app.services.archive_scope import ensure_archive_owner
    from backend.app.services.print_confirmation import OutcomeConflict, outcome_lock, record_outcome
    from backend.app.services.quality_authorization import can_inspect_run

    user, can_modify_all, api_key = auth_result
    if run_id is not None and outcome.run_id != run_id:
        raise HTTPException(409, "The selected run does not match the inspection")
    async with outcome_lock(db, archive_id, run_id):
        archive = ensure_archive_owner(await db.get(PrintArchive, archive_id), auth_result)
        selected = await db.get(PrintLogEntry, outcome.run_id)
        historical = run_id is not None
        if not can_inspect_run(user, can_modify_all, archive, selected, historical=historical):
            raise HTTPException(404, "Print run not found")
        if api_key is not None and api_key.printer_ids is not None:
            printers = [selected.printer_id]
            if not historical or selected.started_at is None:
                printers.append(archive.printer_id)
            if any(printer_id is not None and printer_id not in api_key.printer_ids for printer_id in printers):
                raise HTTPException(404, "Print run not found")
        try:
            run = await record_outcome(
                db,
                archive,
                source="api_key" if api_key else "dialog",
                historical=run_id is not None,
                **outcome.model_dump(),
            )
        except OutcomeConflict as error:
            raise HTTPException(409, str(error)) from error
        await db.commit()
        return {
            "run_id": run.id,
            "user_verdict": run.user_verdict,
            "good_quantity": run.good_quantity,
            "reject_quantity": run.reject_quantity,
        }


async def production_outcome_link_page(request: Request, token: str, verdict: str, db: AsyncSession):
    """Read-only landing page; unfurlers never record an inspection through GET."""
    from backend.app.api.confirmation_pages import confirmation_page
    from backend.app.services.print_confirmation import find_token_run

    match = await find_token_run(db, token) if verdict in {"good", "reject"} else None
    if match is None:
        raise HTTPException(404, "Confirmation link is invalid or has expired")
    return confirmation_page(request, match[1], verdict)


async def confirm_production_outcome_link(request: Request, token: str, verdict: str, db: AsyncSession):
    """An expiring capability can answer just this run, once, with no other authority."""
    from backend.app.api.confirmation_pages import confirmation_page
    from backend.app.services.print_confirmation import (
        OutcomeConflict,
        find_token_run,
        outcome_lock,
        record_outcome,
        token_digest,
    )

    match = await find_token_run(db, token) if verdict in {"good", "reject"} else None
    if match is None:
        raise HTTPException(404, "Confirmation link is invalid or has expired")
    async with outcome_lock(db, match[0].id, match[1].id):
        match = await find_token_run(db, token)
        if match is None:
            raise HTTPException(404, "Confirmation link is invalid or has expired")
        archive, run = match
        if run.confirm_token_used_at is not None or run.good_quantity is not None:
            return confirmation_page(request, run, verdict)
        try:
            await record_outcome(
                db,
                archive,
                run_id=run.id,
                source="link",
                token_hash=token_digest(token),
                historical=bool(run.confirm_token_run_scoped),
                good_quantity=run.quantity if verdict == "good" else 0,
                reject_quantity=run.quantity if verdict == "reject" else 0,
            )
        except OutcomeConflict as error:
            raise HTTPException(409, str(error)) from error
        await db.commit()
        return confirmation_page(request, run, verdict, saved=True)
