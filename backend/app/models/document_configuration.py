"""Relational, versioned configuration for commercial documents."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
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


class DocumentConfiguration(Base):
    __tablename__ = "document_configurations"
    __table_args__ = (
        UniqueConstraint(
            "business_profile_id",
            "document_type",
            "language",
            "version",
            name="uq_document_configuration_version",
        ),
        CheckConstraint(
            "status IN ('draft','scheduled','active','superseded')",
            name="ck_document_configuration_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"),
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(32), index=True)
    language: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    basic_policy: Mapped[DocumentBasicPolicy | None] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )
    payment_policy: Mapped[PaymentPolicy | None] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )
    dunning_policy: Mapped[DunningPolicy | None] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )
    text_blocks: Mapped[list[DocumentTextBlock]] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DocumentTextBlock.position",
    )
    content_policy: Mapped[DocumentContentPolicy | None] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )
    tax_policy: Mapped[TaxPolicy | None] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )
    einvoice_policy: Mapped[EInvoicePolicy | None] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )
    publication: Mapped[ConfigurationPublication | None] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )


class DocumentBasicPolicy(Base):
    __tablename__ = "document_basic_policies"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_configurations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    subject: Mapped[str] = mapped_column(String(500), default="")
    validity_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_rule: Mapped[str] = mapped_column(String(32), default="issue_date")
    rounding_mode: Mapped[str] = mapped_column(String(32), default="half_up")
    reference_requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    allowed_successors: Mapped[list] = mapped_column(JSON, default=list)

    configuration: Mapped[DocumentConfiguration] = relationship(back_populates="basic_policy")


class PaymentPolicy(Base):
    __tablename__ = "payment_policies"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_configurations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    payment_term_days: Mapped[int] = mapped_column(Integer, default=14)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    due_date_basis: Mapped[str] = mapped_column(String(32), default="issue_date")
    payment_methods: Mapped[list] = mapped_column(JSON, default=list)
    early_payment_rules: Mapped[list] = mapped_column(JSON, default=list)
    prepayment_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    installment_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    bank_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_profile_bank_accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    use_term_in_invoice_text: Mapped[bool] = mapped_column(Boolean, default=True)

    configuration: Mapped[DocumentConfiguration] = relationship(back_populates="payment_policy")


class DunningPolicy(Base):
    __tablename__ = "dunning_policies"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_configurations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    annual_interest_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=Decimal("0"))
    flat_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    configuration: Mapped[DocumentConfiguration] = relationship(back_populates="dunning_policy")
    stages: Mapped[list[DunningStage]] = relationship(
        back_populates="policy",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DunningStage.level",
    )


class DunningStage(Base):
    __tablename__ = "dunning_stages"
    __table_args__ = (
        UniqueConstraint("dunning_policy_id", "level", name="uq_dunning_stage_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dunning_policy_id: Mapped[int] = mapped_column(
        ForeignKey("dunning_policies.configuration_id", ondelete="CASCADE"),
        index=True,
    )
    level: Mapped[int] = mapped_column(Integer)
    wait_days: Mapped[int] = mapped_column(Integer)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    charge_interest: Mapped[bool] = mapped_column(Boolean, default=False)
    new_due_days: Mapped[int] = mapped_column(Integer, default=7)
    body: Mapped[str] = mapped_column(Text)
    escalation_hint: Mapped[str | None] = mapped_column(Text, nullable=True)

    policy: Mapped[DunningPolicy] = relationship(back_populates="stages")


class DocumentTextBlock(Base):
    __tablename__ = "document_text_blocks"
    __table_args__ = (
        UniqueConstraint("configuration_id", "purpose", "position", name="uq_document_text_block_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_configurations.id", ondelete="CASCADE"),
        index=True,
    )
    purpose: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
    condition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    configuration: Mapped[DocumentConfiguration] = relationship(back_populates="text_blocks")


class DocumentContentPolicy(Base):
    __tablename__ = "document_content_policies"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_configurations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    include_calculation_data: Mapped[bool] = mapped_column(Boolean, default=True)
    visible_content: Mapped[dict] = mapped_column(JSON, default=dict)

    configuration: Mapped[DocumentConfiguration] = relationship(back_populates="content_policy")


class TaxPolicy(Base):
    __tablename__ = "tax_policies"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_configurations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    allowed_cases: Mapped[list] = mapped_column(JSON, default=list)
    decision_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    allow_override: Mapped[bool] = mapped_column(Boolean, default=False)

    configuration: Mapped[DocumentConfiguration] = relationship(back_populates="tax_policy")


class EInvoicePolicy(Base):
    __tablename__ = "einvoice_policies"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_configurations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    requirement: Mapped[str] = mapped_column(String(32), default="rule_required")
    en16931_version: Mapped[str] = mapped_column(String(32), default="1.3.16")
    cius_name: Mapped[str] = mapped_column(String(32), default="XRechnung")
    cius_version: Mapped[str] = mapped_column(String(32), default="3.0.2")
    syntax: Mapped[str] = mapped_column(String(32), default="ubl_2_1")
    zugferd_profile: Mapped[str] = mapped_column(String(32), default="EN16931")
    process_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_identifier_scheme: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bank_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_profile_bank_accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    recipient_requirements: Mapped[dict] = mapped_column(JSON, default=dict)

    configuration: Mapped[DocumentConfiguration] = relationship(back_populates="einvoice_policy")


class CustomerDocumentPreference(Base):
    __tablename__ = "customer_document_preferences"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "business_profile_id",
            "document_type",
            "language",
            name="uq_customer_document_preference",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"),
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(16), default="de")
    einvoice_preference: Mapped[str] = mapped_column(String(32), default="inherit")
    endpoint_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endpoint_scheme: Mapped[str | None] = mapped_column(String(32), nullable=True)
    buyer_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    leitweg_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    routing_data: Mapped[dict] = mapped_column(JSON, default=dict)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)


class ConfigurationPublication(Base):
    __tablename__ = "configuration_publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_configurations.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    validation_status: Mapped[str] = mapped_column(String(32), default="pending")
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    rule_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    configuration: Mapped[DocumentConfiguration] = relationship(back_populates="publication")
