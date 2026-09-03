"""Sales articles and their independent, append-only warehouse journal."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from backend.app.core.database import Base


class WarehouseDecimal(TypeDecorator):
    """Six decimal places, stored as integer millionths on both supported databases.

    SQLite NUMERIC affinity would silently perform floating point arithmetic.
    Integer storage also makes SUM exact for our bounded stock quantities.
    """

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        scaled = Decimal(str(value)) * 1_000_000
        if not scaled.is_finite() or scaled != scaled.to_integral_value() or abs(scaled) >= 10**18:
            raise ValueError("Value exceeds warehouse decimal precision")
        return int(scaled)

    def process_result_value(self, value, dialect):
        return Decimal(value) / 1_000_000 if value is not None else None


class WarehouseArticle(Base):
    __tablename__ = "warehouse_articles"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("kind IN ('finished','trade','service')", name="ck_warehouse_article_kind"),
        CheckConstraint("stock_source IN ('own','material','none')", name="ck_warehouse_article_source"),
        CheckConstraint(
            "(kind = 'service' AND stock_source = 'none' AND small_part_id IS NULL) OR "
            "(kind != 'service' AND ((stock_source = 'own' AND small_part_id IS NULL) OR "
            "(stock_source = 'material' AND small_part_id IS NOT NULL)))",
            name="ck_warehouse_article_stock_owner",
        ),
        CheckConstraint(
            "minimum_stock >= 0 AND unit_cost >= 0 AND sale_price >= 0 AND tax_rate >= 0",
            name="ck_warehouse_article_prices",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    unit_code: Mapped[str] = mapped_column(ForeignKey("small_part_units.code", ondelete="RESTRICT"))
    sale_price: Mapped[Decimal] = mapped_column(WarehouseDecimal, default=Decimal("0"))
    tax_rate: Mapped[Decimal] = mapped_column(WarehouseDecimal, default=Decimal("0"))
    unit_cost: Mapped[Decimal] = mapped_column(WarehouseDecimal, default=Decimal("0"))
    minimum_stock: Mapped[Decimal] = mapped_column(WarehouseDecimal, default=Decimal("0"))
    stock_source: Mapped[str] = mapped_column(String(16), default="own")
    small_part_id: Mapped[int | None] = mapped_column(ForeignKey("small_parts.id", ondelete="RESTRICT"), unique=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    calculation_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("calculation_revisions.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WarehouseArticleLedgerEntry(Base):
    __tablename__ = "warehouse_article_ledger_entries"
    __table_args__ = (
        UniqueConstraint("article_id", "idempotency_key", name="uq_warehouse_ledger_command"),
        UniqueConstraint("reverses_id", name="uq_warehouse_ledger_reversal"),
        CheckConstraint("physical_delta != 0 OR reserved_delta != 0", name="ck_warehouse_ledger_nonzero"),
        CheckConstraint(
            "entry_kind IN ('opening','receipt','issue','transfer','correction','reservation','release','reserved_issue','counter')",
            name="ck_warehouse_ledger_kind",
        ),
        CheckConstraint(
            "target_location_id IS NULL OR target_location_id != location_id", name="ck_warehouse_transfer_location"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("warehouse_articles.id", ondelete="RESTRICT"), index=True)
    entry_kind: Mapped[str] = mapped_column(String(24))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    target_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    quantity: Mapped[Decimal] = mapped_column(WarehouseDecimal)
    physical_delta: Mapped[Decimal] = mapped_column(WarehouseDecimal)
    reserved_delta: Mapped[Decimal] = mapped_column(WarehouseDecimal)
    unit_code: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("customer_orders.id", ondelete="RESTRICT"))
    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_article_ledger_entries.id", ondelete="RESTRICT"), index=True
    )
    reverses_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_article_ledger_entries.id", ondelete="RESTRICT")
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    command_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


@event.listens_for(WarehouseArticleLedgerEntry, "before_update")
@event.listens_for(WarehouseArticleLedgerEntry, "before_delete")
def _immutable_journal(mapper, connection, target):
    raise ValueError("Warehouse journal entries cannot be changed; create a counter-entry")
