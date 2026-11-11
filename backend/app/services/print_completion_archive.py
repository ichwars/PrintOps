"""Find an untracked completion without confusing a name with a substring."""

from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
from backend.app.services.print_completion_identity import (
    _event_subtask_id,
    subtask_name_from_filename,
    subtask_names_match,
)
from backend.app.services.running_print_archive import job_id


async def find_completion_archive(db, printer_id, data, *, exclude_archives=()):
    current_id = _event_subtask_id(data)
    rows = (
        await db.scalars(
            select(PrintArchive)
            .where(
                PrintArchive.printer_id == printer_id,
                PrintArchive.status == "printing",
                PrintArchive.deleted_at.is_(None),
                PrintArchive.id.not_in(exclude_archives),
            )
            .order_by(PrintArchive.created_at.desc(), PrintArchive.id.desc())
        )
    ).all()
    if current_id:
        exact = next((row for row in rows if job_id(row.subtask_id) == current_id), None)
        if exact is not None:
            return exact
    subtask = data.get("subtask_name") or ""
    reported = {subtask, subtask_name_from_filename(subtask)} - {""}
    for archive in rows:
        stored_id = job_id(archive.subtask_id)
        if stored_id and current_id and stored_id != current_id:
            continue
        forms = {archive.print_name or "", subtask_name_from_filename(archive.filename or "")} - {""}
        if any(subtask_names_match(expected, name) for expected in forms for name in reported):
            return archive
        if data.get("filename") and archive.filename == data["filename"]:
            return archive
    return None


async def take_completion_run(db, printer_id, data, bindings, possible_keys):
    """Resolve a durable run before using legacy bindings and archive rows."""
    rows = (
        await db.execute(
            select(PrintLogEntry, PrintArchive.filename)
            .join(PrintArchive, PrintArchive.id == PrintLogEntry.archive_id)
            .where(
                PrintLogEntry.printer_id == printer_id,
                PrintLogEntry.status == RUN_OPEN,
                PrintArchive.deleted_at.is_(None),
            )
            .execution_options(**{INCLUDE_OPEN_RUNS: True})
        )
    ).all()
    explicit_id = data.get("_reconciled_run_id") if data.get("_reconciled") else None
    subtask_id = _event_subtask_id(data)
    if explicit_id is not None:
        active = next((run for run, _ in rows if run.id == explicit_id), None)
        if active is None:
            return None, None, True
    else:
        active = next((run for run, _ in rows if subtask_id and run.subtask_id == subtask_id), None)
        if active is None:
            bound_archives = {bindings[key] for key in possible_keys if key in bindings}
            active = _match_open_run_by_name(rows, data, subtask_id, bound_archives)

    if active is None and subtask_id and not data.get("_reconciled"):
        # A stop while the printer was offline is provisional. Match its late
        # terminal frame only by the actual job ID, never by a reused filename.
        active = await db.scalar(
            select(PrintLogEntry)
            .join(PrintArchive, PrintArchive.id == PrintLogEntry.archive_id)
            .where(
                PrintLogEntry.printer_id == printer_id,
                PrintLogEntry.subtask_id == subtask_id,
                PrintLogEntry.ended_offline.is_(True),
                PrintArchive.deleted_at.is_(None),
            )
            .order_by(PrintLogEntry.id.desc())
            .limit(1)
        )
    protected = {run.archive_id for run, _ in rows}
    archive_id = (
        active.archive_id
        if active is not None
        else next((bindings[key] for key in possible_keys if key in bindings and bindings[key] not in protected), None)
    )
    if archive_id is None:
        archive = await find_completion_archive(db, printer_id, data, exclude_archives=protected)
        archive_id = archive.id if archive is not None else None
    previous_run = (
        bool(rows) if active is None else bool(active.ended_offline or any(run.id > active.id for run, _ in rows))
    )
    if archive_id is not None and not previous_run:
        for key in [key for key, value in bindings.items() if key[0] == printer_id and value == archive_id]:
            bindings.pop(key)
    return archive_id, active, previous_run


def _match_open_run_by_name(rows, data, subtask_id, bound_archives):
    observed = {
        subtask_name_from_filename(name)
        for name in (data.get("subtask_name"), data.get("filename"))
        if isinstance(name, str) and name
    }
    matches = [
        run
        for run, filename in rows
        if run.archive_id in bound_archives
        and (not subtask_id or not run.subtask_id)
        and any(
            subtask_names_match(expected, name)
            for expected in (run.print_name, subtask_name_from_filename(filename))
            if expected
            for name in observed
        )
    ]
    return matches[0] if len(matches) == 1 else None
