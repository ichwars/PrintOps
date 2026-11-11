"""Resolve display metadata separately from evidence needed for object control."""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from sqlalchemy import or_, select

from backend.app.models.active_print_session import ActivePrintSession
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import PrintLogEntry
from backend.app.services.print_completion_identity import subtask_name_from_filename
from backend.app.services.print_log_run import open_print_runs
from backend.app.utils.safe_path import PathTraversalError, safe_join_under

logger = logging.getLogger(__name__)


def job_id(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    result = str(value).strip()
    return result if result not in ("", "0") else None


def normalise(name):
    return name.strip().replace(" ", "_").casefold()


def reported_names(state):
    names = set()
    for field in ("subtask_name", "current_print", "gcode_file", "current_project_url"):
        raw = getattr(state, field, None)
        if not isinstance(raw, str) or not raw.strip():
            continue
        for value in (raw, PurePosixPath(raw.split("://", 1)[-1]).name):
            names.update(normalise(name) for name in (value, f"{value}.3mf", f"{value}.gcode.3mf"))
    return names


def archive_names(archive):
    names = set()
    for raw in (archive.filename, archive.print_name):
        if isinstance(raw, str) and raw:
            names.add(normalise(raw))
            names.add(normalise(PurePosixPath(raw).name))
    if isinstance(archive.filename, str):
        names.add(normalise(subtask_name_from_filename(archive.filename)))
    return names - {""}


async def find_open_print(db, printer_id, current_id, *, reported=()):
    query = (
        open_print_runs(printer_id)
        .add_columns(PrintArchive)
        .join(PrintArchive, PrintArchive.id == PrintLogEntry.archive_id)
        .where(PrintArchive.deleted_at.is_(None))
    )
    if current_id:
        row = (
            await db.execute(
                query.where(PrintLogEntry.subtask_id == current_id).order_by(PrintLogEntry.id.desc()).limit(1)
            )
        ).first()
        return (row[1], row[0]) if row is not None else (None, None)
    if not reported:
        return None, None
    rows = (
        await db.execute(query.where(or_(PrintLogEntry.subtask_id.is_(None), PrintLogEntry.subtask_id == "0")))
    ).all()
    matches = [
        (archive, run)
        for run, archive in rows
        if archive_names(archive) & reported or normalise(run.print_name or "") in reported
    ]
    return matches[0] if len(matches) == 1 else (None, None)


async def find_running_archive(db, printer_id, state, *, bindings, printing_only=True, by_name=False):
    archive, _ = await find_running_print(
        db, printer_id, state, bindings=bindings, printing_only=printing_only, by_name=by_name
    )
    return archive


async def find_running_print(db, printer_id, state, *, bindings, printing_only=True, by_name=False):
    raw_id = getattr(state, "subtask_id", None)
    current_id = job_id(raw_id)
    reported = reported_names(state)
    archive, run = await find_open_print(
        db, printer_id, current_id, reported=reported if by_name and str(raw_id) == "0" else ()
    )
    if archive is not None:
        return archive, run
    if current_id:
        query = select(PrintArchive).where(
            PrintArchive.printer_id == printer_id,
            PrintArchive.subtask_id == current_id,
            PrintArchive.deleted_at.is_(None),
        )
        if printing_only:
            query = query.where(PrintArchive.status == "printing")
        archive = await db.scalar(query.order_by(PrintArchive.created_at.desc(), PrintArchive.id.desc()).limit(1))
        if archive is not None:
            return archive, None

    bound_ids = {
        value
        for (pid, name), value in bindings.items()
        if pid == printer_id and isinstance(name, str) and normalise(name) in reported
    }
    if len(bound_ids) == 1:
        bound = next(iter(bound_ids))
        query = select(PrintArchive).where(PrintArchive.id == bound, PrintArchive.deleted_at.is_(None))
        if printing_only:
            query = query.where(PrintArchive.status == "printing")
        archive = await db.scalar(query)
        if archive is not None:
            stored_id = job_id(archive.subtask_id)
            if current_id and stored_id != current_id and (stored_id is not None or not by_name):
                # Parallel printers can share a source archive whose latest
                # row fields describe the other printer. Require this printer's
                # durable session to vouch for that exception.
                session = await db.get(ActivePrintSession, printer_id)
                if (
                    session is None
                    or job_id(session.subtask_id) != current_id
                    or normalise(session.print_name) not in archive_names(archive)
                ):
                    return None, None
            return archive, None

    # A name is enough for a label/cover, never enough to offer skip objects.
    if not by_name or str(raw_id) != "0" or not reported:
        return None, None
    rows = (
        await db.execute(
            select(PrintArchive)
            .where(
                PrintArchive.printer_id == printer_id,
                PrintArchive.status == "printing",
                PrintArchive.deleted_at.is_(None),
                or_(PrintArchive.subtask_id.is_(None), PrintArchive.subtask_id.in_(("", "0"))),
            )
            .order_by(PrintArchive.created_at.desc(), PrintArchive.id.desc())
        )
    ).scalars()
    archive = next((archive for archive in rows if archive_names(archive) & reported), None)
    return archive, None


def local_archive_file(archive, base_dir):
    if archive is None or not isinstance(archive.file_path, str) or not archive.file_path:
        return None
    try:
        path = safe_join_under(base_dir, archive.file_path, http=False)
    except PathTraversalError:
        logger.warning("Refusing an unsafe running archive path for archive %s", archive.id)
        return None
    return path if path.is_file() and path.suffix.lower() == ".3mf" else None
