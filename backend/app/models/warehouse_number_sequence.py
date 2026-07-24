from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class WarehouseNumberSequence(Base):
    __tablename__ = "warehouse_number_sequences"
    __table_args__ = (
        UniqueConstraint("key", name="uq_warehouse_number_sequence_key"),
        CheckConstraint("next_value > 0", name="ck_warehouse_number_sequence_next_value"),
        CheckConstraint(
            "reset_policy IN ('none', 'yearly')",
            name="ck_warehouse_number_sequence_reset_policy",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), default="")
    pattern: Mapped[str] = mapped_column(String(100), default="{PREFIX}-{#####}")
    next_value: Mapped[int] = mapped_column(Integer, default=1)
    reset_policy: Mapped[str] = mapped_column(String(16), default="none")
    current_period: Mapped[str | None] = mapped_column(String(8), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
