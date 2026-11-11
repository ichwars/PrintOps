"""Shared owner and printer scope for print-run inspection."""

from backend.app.core.auth import user_can_access_printer


def can_inspect_run(user, can_modify_all, archive, run, *, historical=False):
    if archive is None or archive.deleted_at is not None or run is None or run.archive_id != archive.id:
        return False
    exact_run = historical and run.started_at is not None and run.printer_id is not None
    if not can_modify_all:
        if user is None or archive.created_by_id != user.id:
            return False
        if exact_run and run.created_by_id not in (None, user.id):
            return False
    return user_can_access_printer(user, run.printer_id) and (
        exact_run or user_can_access_printer(user, archive.printer_id)
    )
