from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
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


class CalculationProjectFile(Base):
    __tablename__ = "calculation_project_files"
    __table_args__ = (
        UniqueConstraint("calculation_id", "revision_number", name="uq_calculation_project_file_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculations.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    analysis_error: Mapped[str | None] = mapped_column(Text)
    printer_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    calculation = relationship("Calculation", back_populates="project_files")
    plates: Mapped[list[CalculationProjectPlate]] = relationship(
        back_populates="project_file",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CalculationProjectPlate.plate_index",
    )


class CalculationProjectPlate(Base):
    __tablename__ = "calculation_project_plates"
    __table_args__ = (
        UniqueConstraint("project_file_id", "plate_index", name="uq_calculation_project_plate_index"),
        UniqueConstraint("project_file_id", "stable_key", name="uq_calculation_project_plate_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_file_id: Mapped[int] = mapped_column(
        ForeignKey("calculation_project_files.id", ondelete="CASCADE"), index=True
    )
    plate_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stable_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    detected_materials: Mapped[list] = mapped_column(JSON, default=list)
    detected_grams: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    detected_hours: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    geometry: Mapped[dict] = mapped_column(JSON, default=dict)

    project_file: Mapped[CalculationProjectFile] = relationship(back_populates="plates")


class CalculationVariantPlate(Base):
    __tablename__ = "calculation_variant_plates"
    __table_args__ = (
        UniqueConstraint("variant_id", "project_plate_id", name="uq_calculation_variant_plate"),
        CheckConstraint(
            "good_parts >= 0 AND parts_per_print > 0 AND scrap_prints >= 0",
            name="ck_calculation_variant_plate_counts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("calculation_variants.id", ondelete="CASCADE"), index=True)
    project_plate_id: Mapped[int] = mapped_column(
        ForeignKey("calculation_project_plates.id", ondelete="RESTRICT"), index=True
    )
    good_parts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parts_per_print: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scrap_prints: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    material_code: Mapped[str | None] = mapped_column(String(120))
    grams_per_print: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    hours_per_print: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    variant = relationship("CalculationVariant", back_populates="plates")
    project_plate: Mapped[CalculationProjectPlate] = relationship(lazy="selectin")


class CalculationVariantSmallPart(Base):
    __tablename__ = "calculation_variant_small_parts"
    __table_args__ = (
        UniqueConstraint("variant_id", "small_part_id", name="uq_calculation_variant_small_part"),
        CheckConstraint("quantity > 0", name="ck_calculation_variant_small_part_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("calculation_variants.id", ondelete="CASCADE"), index=True)
    small_part_id: Mapped[int] = mapped_column(ForeignKey("small_parts.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    description_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_code_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    variant = relationship("CalculationVariant", back_populates="small_parts")
    small_part = relationship("SmallPart", lazy="selectin")
