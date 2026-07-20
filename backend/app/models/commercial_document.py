"""Relational aggregate and immutable issuance evidence for commercial documents."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class ImmutableDocumentError(RuntimeError):
    """Raised when append-only document evidence would be rewritten."""


class CommercialDocument(Base):
    __tablename__ = "commercial_documents"
    __table_args__ = (
        UniqueConstraint(
            "business_profile_id",
            "number",
            name="uq_commercial_document_profile_number",
        ),
        CheckConstraint(
            "technical_status IN "
            "('draft','validation_failed','ready','issued','cancelled','corrected','replaced')",
            name="ck_commercial_document_technical_status",
        ),
        CheckConstraint(
            "payment_status IN "
            "('not_applicable','unpaid','partially_paid','paid','overpaid','written_off')",
            name="ck_commercial_document_payment_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_type: Mapped[str] = mapped_column(String(32), index=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"),
        index=True,
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_offer_id: Mapped[int | None] = mapped_column(
        ForeignKey("offers.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    source_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_issuer_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    technical_status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    business_status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    payment_status: Mapped[str] = mapped_column(String(24), default="not_applicable", index=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    service_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    language: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    open_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    content_options: Mapped[dict] = mapped_column(JSON, default=dict)
    tax_decision: Mapped[dict] = mapped_column(JSON, default=dict)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    lines: Mapped[list[CommercialDocumentLine]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CommercialDocumentLine.position",
    )
    outgoing_relations: Mapped[list[DocumentRelation]] = relationship(
        foreign_keys="DocumentRelation.source_document_id",
        back_populates="source_document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    incoming_relations: Mapped[list[DocumentRelation]] = relationship(
        foreign_keys="DocumentRelation.target_document_id",
        back_populates="target_document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    snapshot: Mapped[DocumentSnapshot | None] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )
    artifacts: Mapped[list[DocumentArtifact]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    number_reservations: Mapped[list[DocumentNumberReservation]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    source_offer = relationship(
        "Offer",
        foreign_keys=[source_offer_id],
        back_populates="commercial_document",
    )
    source_order = relationship(
        "CustomerOrder",
        foreign_keys=[source_order_id],
        back_populates="commercial_documents",
    )


class CommercialDocumentLine(Base):
    __tablename__ = "commercial_document_lines"
    __table_args__ = (
        UniqueConstraint("document_id", "position", name="uq_commercial_document_line_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("commercial_documents.id", ondelete="CASCADE"),
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unit_code: Mapped[str] = mapped_column(String(16))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    tax_category_code: Mapped[str] = mapped_column(String(8))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    product_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_data: Mapped[dict] = mapped_column(JSON, default=dict)
    internal_calculation: Mapped[dict] = mapped_column(JSON, default=dict)

    document: Mapped[CommercialDocument] = relationship(back_populates="lines")


class DocumentRelation(Base):
    __tablename__ = "document_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "target_document_id",
            "relation_type",
            name="uq_document_relation",
        ),
        CheckConstraint(
            "source_document_id <> target_document_id",
            name="ck_document_relation_distinct_documents",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("commercial_documents.id", ondelete="RESTRICT"),
        index=True,
    )
    target_document_id: Mapped[int] = mapped_column(
        ForeignKey("commercial_documents.id", ondelete="CASCADE"),
        index=True,
    )
    relation_type: Mapped[str] = mapped_column(String(32))
    relation_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_document: Mapped[CommercialDocument] = relationship(
        foreign_keys=[source_document_id],
        back_populates="outgoing_relations",
    )
    target_document: Mapped[CommercialDocument] = relationship(
        foreign_keys=[target_document_id],
        back_populates="incoming_relations",
    )


class DocumentSnapshot(Base):
    __tablename__ = "document_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("commercial_documents.id", ondelete="RESTRICT"),
        unique=True,
        index=True,
    )
    canonical_json: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    configuration_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_configurations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    configuration_version: Mapped[int] = mapped_column(Integer)
    tax_rule_version: Mapped[str] = mapped_column(String(64))
    einvoice_rule_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    issued_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    document: Mapped[CommercialDocument] = relationship(back_populates="snapshot")


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"
    __table_args__ = (
        UniqueConstraint("document_id", "kind", name="uq_document_artifact_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("commercial_documents.id", ondelete="RESTRICT"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32))
    content_type: Mapped[str] = mapped_column(String(128))
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="pending")
    validation_report: Mapped[dict] = mapped_column(JSON, default=dict)
    rule_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[CommercialDocument] = relationship(back_populates="artifacts")


class DocumentNumberReservation(Base):
    __tablename__ = "document_number_reservations"
    __table_args__ = (
        UniqueConstraint(
            "business_profile_id",
            "number",
            name="uq_document_number_reservation_profile_number",
        ),
        CheckConstraint(
            "status IN ('reserved','consumed','voided')",
            name="ck_document_number_reservation_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("commercial_documents.id", ondelete="RESTRICT"),
        index=True,
    )
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"),
        index=True,
    )
    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("number_sequences.id", ondelete="RESTRICT"),
        index=True,
    )
    number: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="reserved", index=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped[CommercialDocument] = relationship(back_populates="number_reservations")


def _reject_evidence_change(_mapper, _connection, target) -> None:
    raise ImmutableDocumentError(f"{type(target).__name__} is immutable")


event.listen(DocumentSnapshot, "before_update", _reject_evidence_change)
event.listen(DocumentSnapshot, "before_delete", _reject_evidence_change)
