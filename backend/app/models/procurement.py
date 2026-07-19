from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(80))
    website: Mapped[str | None] = mapped_column(String(2048))
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    customer_number: Mapped[str | None] = mapped_column(String(120))
    payment_terms: Mapped[str | None] = mapped_column(String(500))
    default_lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProcurementOffer(Base):
    __tablename__ = "procurement_offers"
    __table_args__ = (
        CheckConstraint(
            "(small_part_id IS NOT NULL AND filament_sku_settings_id IS NULL) OR "
            "(small_part_id IS NULL AND filament_sku_settings_id IS NOT NULL)",
            name="ck_procurement_offer_target",
        ),
        CheckConstraint(
            "package_quantity > 0 AND minimum_order_quantity > 0 AND lead_time_days >= 0 "
            "AND net_price >= 0 AND gross_price >= 0",
            name="ck_procurement_offer_values",
        ),
        Index(
            "uq_procurement_offer_preferred_resource",
            "resource_key",
            unique=True,
            sqlite_where=text("is_preferred = 1 AND is_active = 1"),
            postgresql_where=text("is_preferred = true AND is_active = true"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    small_part_id: Mapped[int | None] = mapped_column(ForeignKey("small_parts.id", ondelete="RESTRICT"), index=True)
    filament_sku_settings_id: Mapped[int | None] = mapped_column(
        ForeignKey("filament_sku_settings.id", ondelete="RESTRICT"), index=True
    )
    resource_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(255))
    purchase_url: Mapped[str | None] = mapped_column(String(2048))
    package_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("1"))
    package_unit_code: Mapped[str] = mapped_column(String(16), nullable=False, default="C62")
    minimum_order_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("1"))
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    gross_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
