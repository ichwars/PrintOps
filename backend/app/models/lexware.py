"""Connection secrets and external master-data snapshots, separate from local records."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class LexwareConnection(Base):
    __tablename__ = "lexware_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"), unique=True
    )
    organization_id: Mapped[str] = mapped_column(String(36), unique=True)
    company_name: Mapped[str] = mapped_column(String(255))
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sync_status: Mapped[str] = mapped_column(String(24), default="idle")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LexwareResource(Base):
    __tablename__ = "lexware_resources"
    __table_args__ = (
        UniqueConstraint("connection_id", "kind", "external_id", name="uq_lexware_resource_external"),
        UniqueConstraint("connection_id", "customer_id", name="uq_lexware_resource_customer"),
        UniqueConstraint("connection_id", "article_id", name="uq_lexware_resource_article"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("lexware_connections.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    version_hash: Mapped[str] = mapped_column(String(64))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("warehouse_articles.id", ondelete="RESTRICT"))
    imported_hash: Mapped[str | None] = mapped_column(String(64))
    imported_baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
