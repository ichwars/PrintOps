"""Printer scope for an archive that has been printed on more than one printer."""

from fastapi import HTTPException
from sqlalchemy import and_, case, false, func, or_, select

from backend.app.core.auth import OwnershipAccess, check_printer_access, user_can_access_printer
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import PrintLogEntry


def _history_matches(condition):
    runs = PrintLogEntry.__table__
    return select(runs.c.id).where(runs.c.archive_id == PrintArchive.id, condition).correlate(PrintArchive).exists()


def archive_history_printers(printer_ids):
    return _history_matches(PrintLogEntry.__table__.c.printer_id.in_(printer_ids))


def archive_printed_on(printer_id):
    return or_(PrintArchive.printer_id == printer_id, archive_history_printers([printer_id]))


def archive_printer_conditions(access: OwnershipAccess, *, include_runs: bool = False):
    scope = access.printer_ids
    if scope is None:
        return ()
    conditions = [PrintArchive.printer_id.in_(scope)]
    if access.api_key is None or access.api_key.printer_ids is None:
        conditions.append(PrintArchive.printer_id.is_(None))
    if include_runs:
        conditions.append(archive_history_printers(scope))
    return (or_(*conditions),)


def archive_visibility_conditions(access: OwnershipAccess):
    conditions = archive_printer_conditions(access, include_runs=True)
    if access.can_access_all:
        return conditions
    owner = PrintArchive.created_by_id == access.user.id if access.user is not None else false()
    return (*conditions, owner)


def whole_archive_conditions(access: OwnershipAccess):
    conditions = list(archive_printer_conditions(access))
    runs = PrintLogEntry.__table__.c
    scope = access.printer_ids
    if scope is not None:
        printer = runs.printer_id
        forbidden = and_(printer.is_not(None), printer.not_in(scope))
        if access.api_key is not None and access.api_key.printer_ids is not None:
            forbidden = or_(printer.is_(None), printer.not_in(scope))
        conditions.append(~_history_matches(forbidden))
    if not access.can_access_all:
        if access.user is None:
            return (false(),)
        other_owner = and_(runs.created_by_id.is_not(None), runs.created_by_id != access.user.id)
        conditions.append(~_history_matches(other_owner))
    return tuple(conditions)


def archive_status_in_scope(access):
    scope = access.printer_ids
    whole = whole_archive_conditions(access)
    if not whole:
        return PrintArchive.status
    runs = PrintLogEntry.__table__.c
    filters = [runs.archive_id == PrintArchive.id]
    if scope is not None:
        filters.append(runs.printer_id.in_(scope))
    if not access.can_access_all:
        filters.append(runs.created_by_id == access.user.id if access.user is not None else false())
    latest = (
        select(runs.status)
        .where(*filters)
        .order_by(runs.started_at.desc().nulls_last(), runs.id.desc())
        .limit(1)
        .correlate(PrintArchive)
        .scalar_subquery()
    )
    return case((and_(*whole), PrintArchive.status), else_=func.coalesce(latest, "archived"))


def ensure_archive_owner(archive: PrintArchive | None, access: OwnershipAccess) -> PrintArchive:
    if archive is None or archive.deleted_at is not None:
        raise HTTPException(404, "Archive not found")
    if not access.can_access_all and (access.user is None or archive.created_by_id != access.user.id):
        raise HTTPException(404, "Archive not found")
    return archive


def ensure_current_archive_visible(archive: PrintArchive | None, access: OwnershipAccess) -> PrintArchive:
    archive = ensure_archive_owner(archive, access)
    if not user_can_access_printer(access.user, archive.printer_id):
        raise HTTPException(404, "Archive not found")
    if access.api_key is not None:
        check_printer_access(access.api_key, archive.printer_id)
    return archive


async def ensure_archive_visible(db, archive: PrintArchive | None, access: OwnershipAccess) -> PrintArchive:
    archive = ensure_archive_owner(archive, access)
    if (
        access.printer_ids is None
        or await db.scalar(
            select(PrintArchive.id).where(PrintArchive.id == archive.id, *archive_visibility_conditions(access))
        )
        is not None
    ):
        return archive
    return ensure_current_archive_visible(archive, access)


async def ensure_whole_archive_visible(db, archive: PrintArchive, access: OwnershipAccess) -> None:
    conditions = whole_archive_conditions(access)
    if (
        conditions
        and await db.scalar(select(PrintArchive.id).where(PrintArchive.id == archive.id, *conditions)) is None
    ):
        raise HTTPException(403, "This archive includes prints outside your access")
