from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("business_profile_id", "number", name="uq_offer_profile_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"), index=True
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    calculation_revision_id: Mapped[int] = mapped_column(
        ForeignKey("calculation_revisions.id", ondelete="RESTRICT"), index=True
    )
    number: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    preferred_variant_sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    calculation_revision = relationship("CalculationRevision", lazy="selectin")
    customer = relationship("Customer", lazy="selectin")
    business_profile = relationship("BusinessProfile", lazy="selectin")
    order: Mapped[CustomerOrder | None] = relationship(back_populates="offer", uselist=False, lazy="selectin")
    commercial_document = relationship(
        "CommercialDocument",
        back_populates="source_offer",
        uselist=False,
        lazy="selectin",
    )

    @property
    def order_id(self) -> int | None:
        return self.order.id if self.order is not None else None


class CustomerOrder(Base):
    __tablename__ = "customer_orders"
    __table_args__ = (UniqueConstraint("business_profile_id", "number", name="uq_order_profile_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"), index=True
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="RESTRICT"), unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), unique=True)
    number: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    accepted_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    offer: Mapped[Offer] = relationship(back_populates="order", lazy="selectin")
    project = relationship("Project", lazy="selectin")
    reservations = relationship("StockReservation", back_populates="order", lazy="selectin")
    commercial_documents = relationship(
        "CommercialDocument",
        back_populates="source_order",
        lazy="selectin",
    )


class OfferAcceptance(Base):
    __tablename__ = "offer_acceptances"

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="RESTRICT"), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("customer_orders.id", ondelete="RESTRICT"), unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    offer = relationship("Offer", lazy="selectin")
    order = relationship("CustomerOrder", lazy="selectin")
    project = relationship("Project", lazy="selectin")
