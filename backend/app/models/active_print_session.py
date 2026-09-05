"""Durable filament-attribution context for an in-flight print."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class ActivePrintSession(Base):
    """Print-start evidence needed by completion, persisted per printer."""

    __tablename__ = "active_print_sessions"

    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), primary_key=True)
    print_name: Mapped[str] = mapped_column(default="")
    subtask_id: Mapped[str | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    tray_now_at_start: Mapped[int] = mapped_column(default=-1)
    plate_id: Mapped[int | None] = mapped_column(nullable=True)
    ams_mapping: Mapped[list | None] = mapped_column(JSON, nullable=True)
    spool_assignments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tray_remain_start: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tray_change_log: Mapped[list | None] = mapped_column(JSON, nullable=True)
    spoolman_owns_usage: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
