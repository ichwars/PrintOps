from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class SmallPartCategory(Base):
    __tablename__ = "small_part_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SmallPartUnit(Base):
    __tablename__ = "small_part_units"
    __table_args__ = (CheckConstraint("decimal_places BETWEEN 0 AND 6", name="ck_small_part_unit_precision"),)

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SmallPart(Base):
    __tablename__ = "small_parts"
    __table_args__ = (
        CheckConstraint("minimum_stock >= 0", name="ck_small_part_min_stock"),
        CheckConstraint("unit_cost >= 0", name="ck_small_part_unit_cost"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    search_terms: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("small_part_categories.id", ondelete="SET NULL"), index=True
    )
    unit_code: Mapped[str] = mapped_column(
        ForeignKey("small_part_units.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    supplier_reference: Mapped[str | None] = mapped_column(String(255))
    default_consumption_reason: Mapped[str] = mapped_column(String(120), nullable=False, default="Produktion")
    internal_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped[SmallPartCategory | None] = relationship(lazy="selectin")
    unit: Mapped[SmallPartUnit] = relationship(lazy="selectin")
    location = relationship("Location", back_populates="small_parts", lazy="selectin")
    ledger_entries: Mapped[list[SmallPartLedgerEntry]] = relationship(back_populates="small_part", lazy="raise")


class SmallPartLedgerEntry(Base):
    __tablename__ = "small_part_ledger_entries"
    __table_args__ = (
        CheckConstraint("physical_delta != 0 OR reserved_delta != 0", name="ck_small_part_ledger_nonzero"),
        CheckConstraint(
            "entry_kind IN ('opening','receipt','correction','reservation','release','issue')",
            name="ck_small_part_ledger_kind",
        ),
        UniqueConstraint("idempotency_key", name="uq_small_part_ledger_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    small_part_id: Mapped[int] = mapped_column(
        ForeignKey("small_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entry_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    physical_delta: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    reserved_delta: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32))
    reference_id: Mapped[int | None] = mapped_column(Integer)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    small_part: Mapped[SmallPart] = relationship(back_populates="ledger_entries")
