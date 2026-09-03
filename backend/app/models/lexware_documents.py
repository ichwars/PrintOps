"""External vouchers and their evidence never participate in local issuance."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class LexwareDocument(Base):
    __tablename__ = "lexware_documents"
    __table_args__ = (UniqueConstraint("connection_id", "external_id", name="uq_lexware_document_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("lexware_connections.id", ondelete="RESTRICT"), index=True)
    external_id: Mapped[str] = mapped_column(String(36))
    voucher_type: Mapped[str] = mapped_column(String(64))
    voucher_status: Mapped[str] = mapped_column(String(64))
    voucher_number: Mapped[str | None] = mapped_column(String(255))
    voucher_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    contact_name: Mapped[str | None] = mapped_column(String(500))
    currency: Mapped[str] = mapped_column(String(3))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    supported: Mapped[bool] = mapped_column(Boolean)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    in_latest_sync: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    version_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    local_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("commercial_documents.id", ondelete="RESTRICT"), unique=True
    )
    linked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payment: Mapped["LexwarePaymentSnapshot | None"] = relationship(lazy="selectin", uselist=False)


class LexwarePaymentSnapshot(Base):
    __tablename__ = "lexware_payment_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("lexware_documents.id", ondelete="RESTRICT"), unique=True)
    # unknown means the upstream information is absent, unavailable or incomplete.
    state: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict | None] = mapped_column(JSON)


class LexwareOriginal(Base):
    __tablename__ = "lexware_originals"
    __table_args__ = (UniqueConstraint("document_id", "file_id", name="uq_lexware_original_file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("lexware_documents.id", ondelete="RESTRICT"), index=True)
    file_id: Mapped[str] = mapped_column(String(36))
    source_path: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(80))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _reject_original_mutation(_mapper, _connection, _original):
    raise ValueError("Cached Lexware originals are immutable")


event.listen(LexwareOriginal, "before_update", _reject_original_mutation)
event.listen(LexwareOriginal, "before_delete", _reject_original_mutation)
