from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (UniqueConstraint("order_id", "source_key", name="uq_stock_reservation_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("customer_orders.id", ondelete="RESTRICT"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    material_code: Mapped[str | None] = mapped_column(String(120))
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order = relationship("CustomerOrder", back_populates="reservations")
    allocations: Mapped[list[StockReservationAllocation]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan", lazy="selectin"
    )


class StockReservationAllocation(Base):
    __tablename__ = "stock_reservation_allocations"
    __table_args__ = (
        CheckConstraint(
            "(spool_id IS NOT NULL AND external_spool_id IS NULL AND small_part_id IS NULL) OR "
            "(spool_id IS NULL AND external_spool_id IS NOT NULL AND small_part_id IS NULL) OR "
            "(spool_id IS NULL AND external_spool_id IS NULL AND small_part_id IS NOT NULL)",
            name="ck_stock_allocation_exact_target",
        ),
        CheckConstraint(
            "allocated_quantity > 0 AND consumed_quantity >= 0 AND consumed_quantity <= allocated_quantity",
            name="ck_stock_allocation_quantities",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stock_reservations.id", ondelete="CASCADE"), index=True)
    inventory_backend: Mapped[str] = mapped_column(String(16), nullable=False)
    spool_id: Mapped[int | None] = mapped_column(ForeignKey("spool.id", ondelete="RESTRICT"), index=True)
    external_spool_id: Mapped[str | None] = mapped_column(String(120), index=True)
    small_part_id: Mapped[int | None] = mapped_column(ForeignKey("small_parts.id", ondelete="RESTRICT"), index=True)
    allocated_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    consumed_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))

    reservation: Mapped[StockReservation] = relationship(back_populates="allocations")
    spool = relationship("Spool", lazy="selectin")
    small_part = relationship("SmallPart", lazy="selectin")


class StockResourceLock(Base):
    __tablename__ = "stock_resource_locks"

    resource_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    touched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StockReservationCommand(Base):
    __tablename__ = "stock_reservation_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("customer_orders.id", ondelete="RESTRICT"), index=True)
    allocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_reservation_allocations.id", ondelete="RESTRICT"), index=True
    )
    command: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
