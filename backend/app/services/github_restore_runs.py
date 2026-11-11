"""Restore portable print history without reinstating live runs or capabilities."""

from sqlalchemy import or_, select

from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
from backend.app.models.printer import Printer
from backend.app.models.user import User
from backend.app.services.github_restore import _created_at_matches, _parse_dt, _restored_number
from backend.app.services.print_log_run import project_latest_finished_run

_TERMINAL = frozenset({"completed", "failed", "aborted", "cancelled", "stopped", "skipped"})


def backed_up_runs(payload):
    runs = payload.get("runs") if isinstance(payload, dict) else None
    return runs if isinstance(runs, list) else []


def archived_run_starts(payload):
    starts = {}
    for entry in backed_up_runs(payload):
        if isinstance(entry, dict) and type(entry.get("archive_id")) is int:
            started = _parse_dt(entry.get("started_at"))
            if started is not None:
                starts.setdefault(entry["archive_id"], set()).add(started)
    return starts


def _text(entry, name, limit):
    value = entry.get(name)
    return value[:limit] if isinstance(value, str) and value and "\0" not in value else None


def _run_fields(entry, started, printer_id, printer_name, owner, tally):
    numbers = {
        "plate_id": _restored_number(entry.get("plate_id"), integer=True),
        "duration_seconds": _restored_number(entry.get("duration_seconds"), integer=True),
        "filament_used_grams": _restored_number(entry.get("filament_used_grams"), maximum=100_000),
        "cost": _restored_number(entry.get("cost")),
        "energy_kwh": _restored_number(entry.get("energy_kwh")),
        "energy_cost": _restored_number(entry.get("energy_cost")),
        "quantity": _restored_number(entry.get("quantity"), maximum=10_000, integer=True),
        "good_quantity": _restored_number(entry.get("good_quantity"), maximum=10_000, integer=True),
        "reject_quantity": _restored_number(entry.get("reject_quantity"), maximum=10_000, integer=True),
    }
    if any(entry.get(key) is not None and value is None for key, value in numbers.items()):
        tally.note("archivesNumbersDropped", "Invalid numeric values in some print records were omitted")
    quantity = numbers["quantity"] or 1
    good, reject = numbers["good_quantity"], numbers["reject_quantity"]
    source_status = _text(entry, "status", 20)
    backed_up_in_flight = source_status in (RUN_OPEN, "paused")
    status = source_status if source_status in _TERMINAL else "aborted"
    valid_verdict = status == "completed" and good is not None and reject is not None and good + reject == quantity
    verdict = None
    if valid_verdict:
        verdict = "good" if reject == 0 else "reject" if good == 0 else "mixed"
    return {
        **numbers,
        "quantity": quantity,
        "good_quantity": good if valid_verdict else None,
        "reject_quantity": reject if valid_verdict else None,
        "user_verdict": verdict,
        "user_verdict_source": _text(entry, "user_verdict_source", 16) if valid_verdict else None,
        "user_verdict_at": _parse_dt(entry.get("user_verdict_at")) if valid_verdict else None,
        "confirm_requested": status == "completed" and entry.get("confirm_requested") is True,
        "status": status,
        "print_name": _text(entry, "print_name", 255),
        "printer_id": printer_id,
        "printer_name": printer_name,
        "started_at": started,
        "completed_at": _parse_dt(entry.get("completed_at")),
        "duration_unmeasured": True if entry.get("duration_unmeasured") is True or backed_up_in_flight else None,
        "filament_type": _text(entry, "filament_type", 50),
        "filament_color": _text(entry, "filament_color", 200),
        "failure_reason": "noStatusUpdate" if backed_up_in_flight else _text(entry, "failure_reason", 100),
        "created_by_id": owner,
        "created_by_username": _text(entry, "created_by_username", 100) if owner is not None else None,
    }


async def _find_run(db, archive_id, fields, created_at):
    query = (
        select(PrintLogEntry)
        .where(
            PrintLogEntry.archive_id == archive_id,
            PrintLogEntry.started_at == fields["started_at"],
            PrintLogEntry.plate_id == fields["plate_id"],
        )
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )
    name = PrintLogEntry.printer_name == fields["printer_name"]
    if fields["printer_id"] is not None:
        query = query.where(
            or_(PrintLogEntry.printer_id == fields["printer_id"], PrintLogEntry.printer_id.is_(None) & name)
        )
    else:
        query = query.where(name)
    candidates = (await db.scalars(query)).all()
    if fields["started_at"] is None or len(candidates) > 1:
        candidates = [row for row in candidates if _created_at_matches(row, created_at)]
    return candidates[0] if len(candidates) == 1 else None


async def restore_run_records(db, payload, overwrite, tally, archive_ids):
    entries = backed_up_runs(payload)
    if not entries:
        return
    printers = dict((await db.execute(select(Printer.serial_number, Printer.id))).all())
    users = dict((await db.execute(select(User.username, User.id))).all())
    affected = set()
    for entry in entries:
        if not isinstance(entry, dict):
            tally.failed += 1
            continue
        source_archive_id = entry.get("archive_id")
        archive_id = archive_ids.get(source_archive_id) if type(source_archive_id) is int else None
        if source_archive_id is not None and archive_id is None:
            tally.skipped += 1
            tally.note("runsArchiveMissing", "Some runs were skipped because their archives are missing")
            continue
        started, created = _parse_dt(entry.get("started_at")), _parse_dt(entry.get("created_at"))
        if started is None and created is None:
            tally.failed += 1
            continue
        serial = _text(entry, "printer_serial", 100)
        printer_id = printers.get(serial)
        if serial and printer_id is None:
            tally.note("runsPrinterMissing", "Some runs were restored without their original printer")
        owner = users.get(_text(entry, "created_by_username", 100))
        fields = _run_fields(entry, started, printer_id, _text(entry, "printer_name", 255), owner, tally)
        existing = await _find_run(db, archive_id, fields, created)
        if existing is not None:
            if not overwrite or existing.status in (RUN_OPEN, "paused") or entry.get("status") in (RUN_OPEN, "paused"):
                tally.skipped += 1
                continue
            for key, value in fields.items():
                setattr(existing, key, value)
        else:
            db.add(PrintLogEntry(archive_id=archive_id, created_at=created or started, **fields))
        await db.flush()
        if archive_id is not None:
            affected.add(archive_id)
        tally.restored += 1

    for archive_id in sorted(affected):
        archive = await db.get(PrintArchive, archive_id, with_for_update=True)
        if archive is not None:
            await project_latest_finished_run(db, archive)
