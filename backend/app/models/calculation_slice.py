from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class CalculationSliceResult(Base):
    __tablename__ = "calculation_slice_results"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_calculation_slice_cache_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_plate_id: Mapped[int] = mapped_column(
        ForeignKey("calculation_project_plates.id", ondelete="CASCADE"), index=True
    )
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    print_hours: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    material_grams: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    profile_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project_plate = relationship("CalculationProjectPlate", lazy="selectin")
