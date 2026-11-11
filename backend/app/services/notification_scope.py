"""Printer restrictions for notification channels and their logs."""

from sqlalchemy import select

from backend.app.models.notification import NotificationLog, NotificationProvider


def provider_in_scope(printer_id: int | None, printer_scope: set[int] | None) -> bool:
    return printer_scope is None or printer_id in printer_scope


def notification_log_scope(printer_scope: set[int]):
    visible_providers = select(NotificationProvider.id).where(NotificationProvider.printer_id.in_(printer_scope))
    return NotificationLog.printer_id.in_(printer_scope) | (
        NotificationLog.printer_id.is_(None)
        & NotificationLog.printer_name.is_(None)
        & NotificationLog.provider_id.in_(visible_providers)
    )
