"""Distinguish a proven offline outcome from an unknown end time."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
from backend.app.services.running_print_archive import job_id, local_archive_file
from backend.app.utils.local_time import to_naive_utc

logger = logging.getLogger(__name__)


def reconciled_outcome(archive, state, *, run=None):
    terminal = (state.state or "").upper()
    stored = job_id(run.subtask_id if run is not None else archive.subtask_id)
    if terminal not in ("FINISH", "FAILED") or stored is None or stored != job_id(state.subtask_id):
        return "aborted"
    return "completed" if terminal == "FINISH" else "failed"


def reconciled_end_time(archive, now, *, base_dir, plate_id=None, run=None):
    from backend.app.utils.threemf_tools import extract_print_time_from_3mf

    started = to_naive_utc(run.started_at if run is not None else archive.started_at)
    if started is None:
        return None
    plate = plate_id if plate_id is not None else (run.plate_id if run is not None else archive.plate_id)
    estimate = None
    path = local_archive_file(archive, base_dir)
    if path is not None:
        try:
            estimate = extract_print_time_from_3mf(path, plate)
        except Exception as error:
            logger.debug("No plate estimate for reconciled archive %s: %s", archive.id, error)
        if plate is None and estimate != archive.print_time_seconds:
            estimate = None
    elif not archive.file_path and plate is None:
        estimate = archive.print_time_seconds
    if not isinstance(estimate, (int, float)) or isinstance(estimate, bool) or estimate <= 0:
        return None
    return min(started + timedelta(seconds=int(estimate)), to_naive_utc(now))


async def reconciliation_payload(archive, state, now, *, base_dir, plate_id=None, run=None):
    outcome = reconciled_outcome(archive, state, run=run)
    payload = {
        "status": outcome,
        "filename": archive.filename,
        "subtask_name": archive.print_name or "",
        "subtask_id": (run.subtask_id if run is not None else archive.subtask_id) or "",
        "raw_data": state.raw_data or {},
        "_reconciled": True,
    }
    if run is not None:
        payload["_reconciled_run_id"] = run.id
    if outcome != "aborted":
        for source, target in (("progress", "last_progress"), ("layer_num", "last_layer_num")):
            value = getattr(state, source, None)
            if type(value) in (int, float) and value > 0:
                payload[target] = value
    if outcome == "failed":
        fields = ("code", "attr", "module", "severity", "description", "full_code", "actions", "job_id")
        payload["hms_errors"] = [{key: getattr(error, key, None) for key in fields} for error in state.hms_errors or []]
    if outcome == "completed":
        ended = await asyncio.to_thread(
            reconciled_end_time, archive, now, base_dir=base_dir, plate_id=plate_id, run=run
        )
        if ended is not None:
            payload["_reconciled_completed_at"] = ended
    return payload


async def active_prints_to_reconcile(db, printer_id):
    current = await db.execute(
        select(PrintArchive, PrintLogEntry)
        .join(PrintLogEntry, PrintLogEntry.archive_id == PrintArchive.id)
        .where(
            PrintArchive.deleted_at.is_(None),
            PrintLogEntry.status == RUN_OPEN,
            PrintLogEntry.printer_id == printer_id,
        )
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )
    has_open_run = (
        select(PrintLogEntry.id)
        .where(PrintLogEntry.archive_id == PrintArchive.id, PrintLogEntry.status == RUN_OPEN)
        .exists()
    )
    legacy = await db.execute(
        select(PrintArchive)
        .where(
            PrintArchive.printer_id == printer_id,
            PrintArchive.status == "printing",
            PrintArchive.deleted_at.is_(None),
            ~has_open_run,
        )
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )
    return [*current.all(), *((archive, None) for archive in legacy.scalars().all())]
