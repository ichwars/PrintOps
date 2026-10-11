"""Read-only environmental telemetry attached to the existing storage catalog."""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.printer_ha_sensor import LAST_STATE_MAX_LENGTH


class StorageHASensor(Base):
    __tablename__ = "storage_ha_sensors"
    __table_args__ = (UniqueConstraint("location_id", "entity_id"),)

    kind: ClassVar[str] = "numeric"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(255))
    device_class: Mapped[str] = mapped_column(String(32))
    unit: Mapped[str] = mapped_column(String(16))
    alert_above: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_below: Mapped[float | None] = mapped_column(Float, nullable=True)
    notify_on_alert: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    last_state: Mapped[str | None] = mapped_column(String(LAST_STATE_MAX_LENGTH), nullable=True)
    last_changed: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
