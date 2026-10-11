"""Archive run aggregation, response assembly, and outcome confirmation."""

from fastapi import HTTPException, Request
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.api_key import APIKey
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.user import User
from backend.app.schemas.archive import OutcomeConfirmation


def compute_time_accuracy(archive: PrintArchive, run_aggregate: dict | None = None) -> dict:
    """Compute actual print time and accuracy for an archive.

    Returns dict with actual_time_seconds and time_accuracy.
    time_accuracy = (estimated / actual) * 100
    - 100% = perfect estimate
    - >100% = print was faster than estimated
    - <100% = print took longer than estimated

    When ``run_aggregate`` indicates the archive has more than one logged
    run (multi-plate file printed plate-by-plate, or reprints), both
    fields are suppressed: ``archive.started_at / completed_at`` reflect
    the LATEST run only, while ``archive.print_time_seconds`` is the
    whole-file estimate (post-#1593 the parser sums across plates), so
    comparing the two describes different scopes. The card-rendering
    frontend falls through to ``archive.print_time_seconds`` for the
    time display and hides the badge when ``time_accuracy`` is null —
    that's the desired "show estimate, no badge" presentation for
    multi-run archives (#1608). Single-run archives keep the original
    badge behaviour verbatim.
    """
    result: dict[str, int | float | None] = {"actual_time_seconds": None, "time_accuracy": None}

    # Multi-run archives: the per-run actual (started_at..completed_at on
    # the archive row) is incommensurable with the whole-file estimate.
    # Both fields are cleared so the card shows estimate + no badge.
    if run_aggregate and (run_aggregate.get("run_count") or 0) > 1:
        return result

    if archive.started_at and archive.completed_at and archive.status == "completed":
        actual_seconds = int((archive.completed_at - archive.started_at).total_seconds())
        if actual_seconds > 0:
            result["actual_time_seconds"] = actual_seconds

            if archive.print_time_seconds and archive.print_time_seconds > 0:
                # Calculate accuracy as percentage
                accuracy = (archive.print_time_seconds / actual_seconds) * 100
                # Sanity check: skip unreasonable values (e.g., manually changed status)
                # Valid range: 5% to 500% (print took 20x longer to 5x faster than estimated)
                if 5 <= accuracy <= 500:
                    result["time_accuracy"] = round(accuracy, 1)

    return result


async def _load_run_aggregates(db: AsyncSession, archive_ids: list[int]) -> dict[int, dict]:
    """Batch-load per-archive run aggregates from PrintLogEntry.

    Returns ``{archive_id: {run_count, last_run_at, total_filament_actual_grams,
    successful_run_count, failed_run_count}}``. Archives with no logged runs are
    absent from the map; callers should treat that as zero/none.
    """
    from backend.app.models.print_log import PrintLogEntry

    if not archive_ids:
        return {}
    rows = await db.execute(
        select(
            PrintLogEntry.archive_id,
            func.count(PrintLogEntry.id).label("run_count"),
            func.max(PrintLogEntry.started_at).label("last_run_at"),
            func.coalesce(func.sum(PrintLogEntry.filament_used_grams), 0).label("total_filament"),
            func.sum(case((PrintLogEntry.status == "completed", 1), else_=0)).label("successful"),
            func.sum(case((PrintLogEntry.status == "failed", 1), else_=0)).label("failed"),
        )
        .where(PrintLogEntry.archive_id.in_(archive_ids))
        .group_by(PrintLogEntry.archive_id)
    )
    aggregates: dict[int, dict] = {}
    for archive_id, run_count, last_run_at, total_filament, successful, failed in rows.all():
        aggregates[archive_id] = {
            "run_count": int(run_count or 0),
            "last_run_at": last_run_at,
            "total_filament_actual_grams": float(total_filament) if total_filament else None,
            "successful_run_count": int(successful or 0),
            "failed_run_count": int(failed or 0),
        }
    from backend.app.models.print_queue import PrintQueueItem

    latest_ids = (
        select(func.max(PrintLogEntry.id))
        .where(PrintLogEntry.archive_id.in_(archive_ids))
        .group_by(PrintLogEntry.archive_id)
    )
    current = (
        await db.execute(
            select(
                PrintLogEntry.id,
                PrintLogEntry.archive_id,
                PrintLogEntry.quantity,
                PrintQueueItem.batch_id,
            )
            .outerjoin(PrintQueueItem, PrintLogEntry.queue_item_id == PrintQueueItem.id)
            .where(PrintLogEntry.id.in_(latest_ids))
        )
    ).all()
    for run_id, archive_id, quantity, batch_id in current:
        aggregates[archive_id].update(outcome_run_id=run_id, outcome_expected_parts=quantity, outcome_batch_id=batch_id)
    return aggregates


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

    # Add computed time accuracy fields. ``run_aggregate`` lets
    # ``compute_time_accuracy`` suppress the badge for multi-run archives
    # where the per-run actual / whole-file estimate scopes don't match
    # (#1608).
    accuracy_data = archives.compute_time_accuracy(archive, run_aggregate)
    data.update(accuracy_data)

    if run_aggregate:
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
    api_key: APIKey | None,
    auth_result: tuple[User | None, bool],
):
    """Inspect or correct the current run with normal ownership and printer scopes."""
    from backend.app.api.routes import archives
    from backend.app.services.print_confirmation import OutcomeConflict, outcome_lock, record_outcome

    user, can_modify_all = auth_result
    if run_id is not None and outcome.run_id != run_id:
        raise HTTPException(409, "The selected run does not match the inspection")
    async with outcome_lock(db, archive_id, run_id):
        archive = archives._ensure_archive_visible(await db.get(PrintArchive, archive_id), user, can_modify_all)
        selected = await db.get(PrintLogEntry, outcome.run_id)
        if (
            selected is None
            or selected.archive_id != archive_id
            or not archives.user_can_access_printer(user, selected.printer_id)
        ):
            raise HTTPException(404, "Print run not found")
        if api_key is not None and api_key.printer_ids is not None:
            if any(
                printer_id is not None and printer_id not in api_key.printer_ids
                for printer_id in (archive.printer_id, selected.printer_id)
            ):
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
    async with outcome_lock(db, match[0].id):
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
                good_quantity=run.quantity if verdict == "good" else 0,
                reject_quantity=run.quantity if verdict == "reject" else 0,
            )
        except OutcomeConflict as error:
            raise HTTPException(409, str(error)) from error
        await db.commit()
        return confirmation_page(request, run, verdict, saved=True)
