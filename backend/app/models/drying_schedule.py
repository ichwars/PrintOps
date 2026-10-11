"""Persistent daily drying configuration and non-retryable occurrence claims."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class DryingSchedule(Base):
    __tablename__ = "drying_schedules"
    __table_args__ = (
        CheckConstraint("temperature BETWEEN 45 AND 85", name="ck_drying_schedule_temperature"),
        CheckConstraint("duration_hours BETWEEN 1 AND 24", name="ck_drying_schedule_duration"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), index=True)
    ams_id: Mapped[int] = mapped_column(Integer)
    local_time: Mapped[str] = mapped_column(String(5))
    timezone: Mapped[str] = mapped_column(String(100))
    filament: Mapped[str] = mapped_column(String(100))
    temperature: Mapped[int] = mapped_column(Integer)
    duration_hours: Mapped[int] = mapped_column(Integer)
    rotate_tray: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DryingScheduleRun(Base):
    __tablename__ = "drying_schedule_runs"
    __table_args__ = (UniqueConstraint("schedule_id", "occurrence_day", name="uq_drying_schedule_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("drying_schedules.id", ondelete="CASCADE"), index=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), index=True)
    # Unique nullable reservation persists even when delivery/start is uncertain.
    active_printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("printers.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    ams_id: Mapped[int] = mapped_column(Integer)
    occurrence_day: Mapped[str] = mapped_column(String(10))
    module_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    module_firmware: Mapped[str | None] = mapped_column(String(20), nullable=True)
    parameters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    claimed_at: Mapped[datetime] = mapped_column(DateTime)
    publication_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    observed_running_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
