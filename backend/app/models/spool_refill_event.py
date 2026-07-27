from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class SpoolRefillEvent(Base):
    """Audit row for local and Spoolman spool refill operations."""

    __tablename__ = "spool_refill_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    spool_id: Mapped[int | None] = mapped_column(ForeignKey("spool.id", ondelete="SET NULL"), nullable=True, index=True)
    external_spool_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    before_weight_used: Mapped[float] = mapped_column(Float)
    after_weight_used: Mapped[float] = mapped_column(Float)
    added_weight: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
