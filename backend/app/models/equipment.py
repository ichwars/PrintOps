from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_type: Mapped[str] = mapped_column(String(30), default="dryer", index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    acquisition_date: Mapped[date] = mapped_column(Date)
    acquisition_value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    service_years: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    annual_hours: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    maintenance_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))
    nominal_power_watts: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
