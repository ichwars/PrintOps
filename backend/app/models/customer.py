from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base

customer_tag_links = Table(
    "customer_tag_links",
    Base.metadata,
    Column("customer_id", Integer, ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("customer_tags.id", ondelete="CASCADE"), primary_key=True),
)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("kind IN ('company', 'person')", name="ck_customers_kind"),
        CheckConstraint(
            "status IN ('active', 'inactive', 'blocked')",
            name="ck_customers_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    preferred_locale: Mapped[str] = mapped_column(String(16), default="en")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    accounts: Mapped[list[CustomerAccount]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    contacts: Mapped[list[CustomerContact]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    addresses: Mapped[list[CustomerAddress]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tax_identifiers: Mapped[list[CustomerTaxIdentifier]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tags: Mapped[list[CustomerTag]] = relationship(
        secondary=customer_tag_links,
        back_populates="customers",
        lazy="selectin",
    )


class CustomerAccount(Base):
    __tablename__ = "customer_accounts"
    __table_args__ = (
        UniqueConstraint(
            "business_profile_id",
            "number",
            name="uq_customer_account_profile_number",
        ),
        UniqueConstraint(
            "customer_id",
            "business_profile_id",
            name="uq_customer_account_customer_profile",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    number: Mapped[str] = mapped_column(String(50))
    preferred_currency: Mapped[str] = mapped_column(String(3))
    payment_term_days: Mapped[int] = mapped_column(Integer, default=14)
    delivery_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CustomerContact(Base):
    __tablename__ = "customer_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    salutation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    include_on_documents: Mapped[bool] = mapped_column(Boolean, default=False)


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    additional: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street: Mapped[str] = mapped_column(String(255))
    street_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str] = mapped_column(String(32))
    city: Mapped[str] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class CustomerTaxIdentifier(Base):
    __tablename__ = "customer_tax_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "kind",
            "value",
            name="uq_customer_tax_identifier",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(64))
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(16), default="unchecked")


class CustomerTag(Base):
    __tablename__ = "customer_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))

    __table_args__ = (
        UniqueConstraint("name", name="uq_customer_tag_name"),
        Index("uq_customer_tag_name_ci", func.lower(name), unique=True),
    )

    customers: Mapped[list[Customer]] = relationship(
        secondary=customer_tag_links,
        back_populates="tags",
        lazy="selectin",
    )
