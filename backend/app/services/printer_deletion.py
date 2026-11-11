"""Remove printer-bound runtime state after its database deletion commits."""

import asyncio
import logging
from functools import wraps


async def forget_deleted_printer(printer_id: int) -> None:
    from backend.app import main
    from backend.app.api.routes import camera, printers
    from backend.app.services import bambu_ftp, kprofile_drift, layer_timelapse, usage_tracker
    from backend.app.services.automatic_drying_state import clear_pending
    from backend.app.services.obico_detection import obico_detection_service
    from backend.app.services.plate_detection import remove_printer_references
    from backend.app.services.print_scheduler import scheduler

    for state in (
        main._active_prints,
        main._expected_prints,
        main._expected_print_creators,
        main._expected_print_registered_at,
        main._print_ams_mappings,
        main._print_plate_ids,
    ):
        for key in [key for key in state if key[0] == printer_id]:
            state.pop(key)

    offline_notice = main._printer_offline_notify_tasks.pop(printer_id, None)
    if offline_notice is not None:
        offline_notice.cancel()
    photo_producer = main._stage22_finish_in_flight.pop(printer_id, None)
    if photo_producer is not None:
        photo_producer.set()

    for state in (
        main._stage22_finish_frames,
        main._printer_reconciled_since_connect,
        main._last_progress_milestone,
        main._first_layer_notified,
        main._notified_hms_errors,
        main._hms_print_state,
        main._hms_forget_when_gone,
        main._timelapse_baselines,
        main._bed_cool_waiters,
        main._printer_last_connected,
        main._unknown_tag_last_broadcast,
        main._last_status_broadcast,
        main._persisted_firmware_versions,
    ):
        state.pop(printer_id, None)
    main._user_stopped_printers.discard(printer_id)
    main._printer_offline_published.discard(printer_id)
    main._nozzle_count_updated.discard(printer_id)
    for key in [key for key in main._ams_alarm_cooldown if key.partition(":")[0] == str(printer_id)]:
        main._ams_alarm_cooldown.pop(key)

    printers.printer_manager.forget_printer_runtime(printer_id)
    printers.printer_file_cache.forget_printer(printer_id)
    printers.clear_cover_cache(printer_id)
    scheduler.forget_printer(printer_id)
    for state in (
        scheduler._upload_backoff,
        scheduler._upload_refusals,
        scheduler._upload_refusal_notified,
        scheduler._upload_refusal_kind,
        scheduler._dispatch_holds,
        scheduler._drying_in_progress,
        scheduler._drying_owned_ams,
        scheduler._keep_warm.entries,
        scheduler._keep_warm.expired,
    ):
        state.pop(printer_id, None)
    clear_pending(scheduler, printer_id)
    scheduler._ambient_humidity.forget_printer(printer_id)

    usage_tracker.forget_printer(printer_id)
    kprofile_drift.forget_printer(printer_id, deleted=True)
    layer_timelapse.cancel_session(printer_id)
    obico_detection_service.forget_printer(printer_id)
    bambu_ftp.clear_3mf_cache(printer_id)
    remove_printer_references(printer_id)
    if offline_notice is not None:
        await asyncio.gather(offline_notice, return_exceptions=True)
    await camera.forget_printer_camera(printer_id)


async def clear_late_printer_state(printer_id, sessions):
    """Slow print-start work may finish after deletion's normal cleanup."""
    from backend.app.core.printer_lifecycle import printer_exists

    try:
        async with sessions() as db:
            gone = not await printer_exists(db, printer_id)
        if gone:
            await forget_deleted_printer(printer_id)
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not clear deleted printer %s after print start", printer_id, exc_info=True
        )


def clear_state_if_printer_deleted(callback):
    """Retire state a slow callback created after the printer's deletion."""

    @wraps(callback)
    async def cleanup(printer_id, data):
        from backend.app import main

        if await main._ignore_internal_printer_job(printer_id, data, "start"):
            return
        try:
            return await callback(printer_id, data)
        finally:
            await clear_late_printer_state(printer_id, main.async_session)

    return cleanup


def archive_deletion_guard_on_printer(printer_id):
    """Check active queue links unless a shared archive has a durable open run."""
    from sqlalchemy import select

    from backend.app.models.archive import PrintArchive
    from backend.app.models.print_log import RUN_OPEN, PrintLogEntry

    runs = PrintLogEntry.__table__.c
    shared_open_run = (
        select(runs.id)
        .where(runs.archive_id == PrintArchive.id, runs.printer_id != printer_id, runs.status == RUN_OPEN)
        .correlate(PrintArchive)
        .exists()
    )
    return (PrintArchive.printer_id == printer_id) & ~shared_open_run


def exclusive_archives_on_printer(printer_id):
    """Archives and queued copies with no reference to another printer."""
    from sqlalchemy import and_, select

    from backend.app.models.archive import PrintArchive
    from backend.app.models.print_log import PrintLogEntry
    from backend.app.models.print_queue import PrintQueueItem

    # Include open runs, which ORM queries omit by default.
    runs = PrintLogEntry.__table__.c
    other_run = (
        select(runs.id)
        .where(runs.archive_id == PrintArchive.id, runs.printer_id != printer_id)
        .correlate(PrintArchive)
        .exists()
    )
    other_queue = (
        select(PrintQueueItem.id)
        .where(
            PrintQueueItem.archive_id == PrintArchive.id,
            PrintQueueItem.printer_id.is_distinct_from(printer_id),
        )
        .correlate(PrintArchive)
        .exists()
    )
    return and_(PrintArchive.printer_id == printer_id, ~other_run, ~other_queue)


async def detach_printers_archives(db, printer_id):
    """Keep shared files and the currently running print on another printer."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from backend.app.models.archive import PrintArchive
    from backend.app.models.print_log import RUN_OPEN, PrintLogEntry
    from backend.app.services.print_log_run import discard_print_runs, project_latest_finished_run
    from backend.app.services.print_run_media import newest_run

    await discard_print_runs(db, PrintLogEntry.printer_id == printer_id)
    archives = await db.scalars(select(PrintArchive).where(PrintArchive.printer_id == printer_id).with_for_update())
    for archive in archives:
        if archive.status == RUN_OPEN:
            latest = await newest_run(db, archive.id)
            if latest is not None and latest.status == RUN_OPEN:
                archive.printer_id = latest.printer_id
                archive.started_at = latest.started_at
                archive.subtask_id = latest.subtask_id
                archive.plate_id = latest.plate_id
            elif await project_latest_finished_run(db, archive) is None:
                archive.status = "aborted"
                archive.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                archive.failure_reason = "noStatusUpdate"
        if archive.printer_id == printer_id:
            archive.printer_id = None
