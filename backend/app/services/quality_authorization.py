"""Shared owner and printer scope for print-run inspection."""

from backend.app.core.auth import user_can_access_printer


def can_inspect_run(user, can_modify_all, archive, run):
    return bool(
        archive
        and archive.deleted_at is None
        and run
        and run.archive_id == archive.id
        and (can_modify_all or (user is not None and archive.created_by_id == user.id))
        and user_can_access_printer(user, archive.printer_id)
        and user_can_access_printer(user, run.printer_id)
    )
