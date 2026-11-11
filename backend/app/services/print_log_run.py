"""Keep one result per identified print run while preserving production snapshots."""

from sqlalchemy import delete, false, func, or_, select, update

from backend.app.core.row_visibility import RowVisibility
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
from backend.app.models.printer import Printer
from backend.app.utils.local_time import to_naive_utc, utcnow_naive

SNAPSHOT_FIELDS = frozenset({"project_id", "quantity", "confirm_requested"})
KEEP_IF_UNREPORTED = frozenset(
    {
        "queue_item_id",
        "print_name",
        "printer_name",
        "plate_id",
        "subtask_id",
        "energy_start_kwh",
        "energy_start_plug_id",
        "energy_kwh",
        "energy_cost",
        "thumbnail_path",
        "created_by_id",
        "created_by_username",
    }
)


def run_visibility_conditions(access):
    scope = RowVisibility(access.user, access.api_key, access.user is None and access.can_access_all)
    conditions = scope.printer_criteria(PrintLogEntry.printer_id)
    if access.can_access_all:
        return conditions
    owner = PrintLogEntry.created_by_id == access.user.id if access.user is not None else false()
    return (*conditions, owner)


def open_print_runs(printer_id):
    return (
        select(PrintLogEntry)
        .where(PrintLogEntry.printer_id == printer_id, PrintLogEntry.status == RUN_OPEN)
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )


async def entry_of_run(db, archive_id, printer_id, started_at):
    if archive_id is None or printer_id is None or started_at is None:
        return None
    return await db.scalar(
        select(PrintLogEntry)
        .where(
            PrintLogEntry.archive_id == archive_id,
            PrintLogEntry.printer_id == printer_id,
            PrintLogEntry.started_at == to_naive_utc(started_at),
        )
        .order_by(PrintLogEntry.id.desc())
        .limit(1)
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )


async def merge_run_entry(db, fields, *, run_id=None):
    entry = await db.get(PrintLogEntry, run_id, execution_options={INCLUDE_OPEN_RUNS: True}) if run_id else None
    if entry is not None and (entry.archive_id != fields["archive_id"] or entry.printer_id != fields["printer_id"]):
        raise ValueError("Print run does not belong to this archive and printer")
    if entry is None:
        entry = await entry_of_run(db, fields["archive_id"], fields["printer_id"], fields["started_at"])
    if entry is None:
        entry = PrintLogEntry(**fields)
        db.add(entry)
    elif fields["status"] == RUN_OPEN:
        if entry.status == RUN_OPEN and entry.subtask_id is None:
            entry.subtask_id = fields["subtask_id"]
    elif entry.status != fields["status"]:
        if entry.status == RUN_OPEN:
            entry.created_at = utcnow_naive()
        for name, value in fields.items():
            if name in SNAPSHOT_FIELDS or (value is None and name in KEEP_IF_UNREPORTED):
                continue
            setattr(entry, name, value)
    elif entry.duration_unmeasured and not fields["duration_unmeasured"]:
        # A real completion can refine a previously inferred end with the
        # same outcome, without erasing edits or already settled usage.
        for name in ("completed_at", "duration_seconds", "duration_unmeasured", "ended_offline"):
            setattr(entry, name, fields[name])
    return entry


async def record_print_run_start(db, printer, archive, plate_id):
    """Persist this printer's run without rewriting any completed print."""
    from backend.app.models.print_queue import PrintQueueItem
    from backend.app.services.print_log import write_log_entry

    if archive.started_at is None:
        return None, []
    existing = await entry_of_run(db, archive.id, printer.id, archive.started_at)
    if existing is not None:
        if existing.status == RUN_OPEN and existing.subtask_id is None:
            existing.subtask_id = archive.subtask_id
        return None, []
    discarded = await discard_print_runs(
        db, PrintLogEntry.printer_id == printer.id, PrintLogEntry.started_at < to_naive_utc(archive.started_at)
    )
    item = await db.scalar(
        select(PrintQueueItem)
        .where(
            PrintQueueItem.archive_id == archive.id,
            PrintQueueItem.printer_id == printer.id,
            PrintQueueItem.status == "printing",
        )
        .order_by(PrintQueueItem.id.desc())
        .limit(1)
    )
    opened = await write_log_entry(
        db,
        status=RUN_OPEN,
        archive_id=archive.id,
        queue_item_id=item.id if item is not None else None,
        print_name=archive.print_name,
        printer_name=printer.name,
        printer_id=printer.id,
        started_at=archive.started_at,
        plate_id=plate_id if plate_id is not None else item.plate_id if item is not None else archive.plate_id,
        subtask_id=archive.subtask_id,
        filament_type=archive.filament_type,
        filament_color=archive.filament_color,
        thumbnail_path=archive.thumbnail_path,
        created_by_id=item.created_by_id if item is not None else archive.created_by_id,
    )

    opened.photos = []
    for previous in discarded:
        await cancel_discarded_projection(db, previous.archive_id, printer.id, previous.started_at)
    return opened, discarded


async def discard_print_runs(db, *conditions):
    return (
        await db.scalars(
            delete(PrintLogEntry)
            .where(PrintLogEntry.status == RUN_OPEN, *conditions)
            .returning(PrintLogEntry)
            .execution_options(**{INCLUDE_OPEN_RUNS: True})
        )
    ).all()


async def cancel_discarded_projection(db, archive_id, printer_id, started_at):
    """Close a legacy archive projection only when no other run is active."""
    from backend.app.models.archive import PrintArchive

    active = (
        select(PrintLogEntry.id)
        .where(PrintLogEntry.archive_id == archive_id, PrintLogEntry.status == RUN_OPEN)
        .exists()
    )
    await db.execute(
        update(PrintArchive)
        .where(
            PrintArchive.id == archive_id,
            PrintArchive.printer_id == printer_id,
            PrintArchive.started_at == to_naive_utc(started_at),
            PrintArchive.status == RUN_OPEN,
            ~active,
        )
        .values(status="cancelled", failure_reason="noStatusUpdate")
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )


async def record_run_energy_start(db, archive, printer_id, total, plug_id, *, run=None):
    from backend.app.models.archive import PrintArchive

    if run is None:
        run = await entry_of_run(db, archive.id, printer_id, archive.started_at)
    if run is None:
        if archive.printer_id == printer_id:
            archive.energy_start_kwh, archive.energy_start_plug_id = total, plug_id
        return
    if run.status != RUN_OPEN or run.energy_start_kwh is not None:
        return

    run.energy_start_kwh, run.energy_start_plug_id = total, plug_id
    await db.execute(
        update(PrintArchive)
        .where(
            PrintArchive.id == archive.id,
            PrintArchive.printer_id == printer_id,
            PrintArchive.started_at == run.started_at,
        )
        .values(energy_start_kwh=total, energy_start_plug_id=plug_id)
    )


async def other_runs_of(db, archive):
    return (
        await db.execute(
            select(func.count(PrintLogEntry.id)).where(
                PrintLogEntry.archive_id == archive.id,
                or_(
                    PrintLogEntry.started_at.is_(None),
                    PrintLogEntry.started_at != to_naive_utc(archive.started_at),
                    PrintLogEntry.printer_id.is_(None),
                    PrintLogEntry.printer_id != archive.printer_id,
                ),
            )
        )
    ).scalar() or 0


async def project_latest_finished_run(db, archive):
    """Refresh the archive's latest outcome once its printers have finished."""
    if archive.deleted_at is not None:
        return None
    await db.flush()
    running = await db.scalar(
        select(PrintLogEntry.id)
        .where(PrintLogEntry.archive_id == archive.id, PrintLogEntry.status == RUN_OPEN)
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
        .limit(1)
    )
    if running is not None:
        return None
    latest = await db.scalar(
        select(PrintLogEntry)
        .where(PrintLogEntry.archive_id == archive.id)
        .order_by(PrintLogEntry.started_at.desc().nulls_last(), PrintLogEntry.id.desc())
        .limit(1)
    )
    if latest is None:
        return None
    archive.status = latest.status
    archive.started_at, archive.completed_at = latest.started_at, latest.completed_at
    archive.failure_reason = latest.failure_reason
    archive.plate_id = latest.plate_id
    if latest.confirm_requested or latest.user_verdict is not None or latest.photos is not None:
        archive.confirm_requested = latest.confirm_requested
        for field in ("user_verdict", "good_quantity", "reject_quantity", "user_verdict_source", "user_verdict_at"):
            setattr(archive, field, getattr(latest, field))
    if latest.printer_id is not None and latest.printer_id != archive.printer_id:
        if await db.scalar(select(Printer.id).where(Printer.id == latest.printer_id)) is not None:
            archive.printer_id = latest.printer_id
    return latest.status
