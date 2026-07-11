from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base

if TYPE_CHECKING:
    from backend.app.models.business_profile import BusinessProfile


class NumberSequence(Base):
    __tablename__ = "number_sequences"
    __table_args__ = (
        UniqueConstraint("business_profile_id", "key", name="uq_number_sequence_profile_key"),
        CheckConstraint("next_value > 0", name="ck_number_sequence_next_value"),
        CheckConstraint(
            "reset_policy IN ('none', 'yearly')",
            name="ck_number_sequence_reset_policy",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    key: Mapped[str] = mapped_column(String(32))
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

    business_profile: Mapped[BusinessProfile] = relationship(back_populates="number_sequences")
