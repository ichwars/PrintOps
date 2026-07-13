from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class Calculation(Base):
    __tablename__ = "calculations"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"), index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_kind: Mapped[str] = mapped_column(String(24), default="single")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255))
    position_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    commercial_overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    variants: Mapped[list[CalculationVariant]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CalculationVariant.sort_order"
    )
    revisions: Mapped[list[CalculationRevision]] = relationship(
        lazy="selectin", order_by="CalculationRevision.revision_number"
    )
    business_profile = relationship("BusinessProfile", lazy="selectin")
    customer = relationship("Customer", lazy="selectin")
    project = relationship("Project", lazy="selectin")


class CalculationVariant(Base):
    __tablename__ = "calculation_variants"
    __table_args__ = (UniqueConstraint("calculation_id", "name", name="uq_calculation_variant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    price_method: Mapped[str] = mapped_column(String(24), default="target_margin")
    price_rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))

    lines: Mapped[list[CalculationLine]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CalculationLine.sort_order"
    )
    operations: Mapped[list[CalculationOperation]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CalculationOperation.sort_order"
    )


class CalculationLine(Base):
    __tablename__ = "calculation_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("calculation_variants.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1"))
    unit_code: Mapped[str] = mapped_column(String(16), default="C62")
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CalculationOperation(Base):
    __tablename__ = "calculation_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("calculation_variants.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(255))
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_plate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    good_parts: Mapped[int] = mapped_column(Integer, default=1)
    parts_per_run: Mapped[int] = mapped_column(Integer, default=1)
    scrap_runs: Mapped[int] = mapped_column(Integer, default=0)
    material_grams_per_run: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    print_hours_per_run: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    labor: Mapped[list[CalculationLabor]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CalculationLabor.sort_order"
    )


class CalculationLabor(Base):
    __tablename__ = "calculation_labors"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("calculation_operations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    allocation_basis: Mapped[str] = mapped_column(String(16), default="request")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CalculationRevision(Base):
    __tablename__ = "calculation_revisions"
    __table_args__ = (UniqueConstraint("calculation_id", "revision_number", name="uq_calculation_revision_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculations.id", ondelete="RESTRICT"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    production_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalculationTemplate(Base):
    __tablename__ = "calculation_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1)
    definition: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
