from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base

if TYPE_CHECKING:
    from backend.app.models.number_sequence import NumberSequence


class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    __table_args__ = (
        CheckConstraint("length(country_code) = 2", name="ck_business_profiles_country_code"),
        CheckConstraint("length(default_currency) = 3", name="ck_business_profiles_currency"),
        CheckConstraint(
            "billing_mode IN ('internal', 'external', 'hybrid')",
            name="ck_business_profiles_billing_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    legal_name: Mapped[str] = mapped_column(String(255))
    trading_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2))
    default_currency: Mapped[str] = mapped_column(String(3))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    default_locale: Mapped[str] = mapped_column(String(16), default="en")
    billing_mode: Mapped[str] = mapped_column(String(16), default="hybrid")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    addresses: Mapped[list[BusinessProfileAddress]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tax_identifiers: Mapped[list[BusinessProfileTaxIdentifier]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    bank_accounts: Mapped[list[BusinessProfileBankAccount]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    number_sequences: Mapped[list[NumberSequence]] = relationship(
        back_populates="business_profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class BusinessProfileAddress(Base):
    __tablename__ = "business_profile_addresses"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('registered', 'billing', 'shipping', 'other')",
            name="ck_business_profile_address_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )
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


class BusinessProfileTaxIdentifier(Base):
    __tablename__ = "business_profile_tax_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "business_profile_id",
            "kind",
            "value",
            name="uq_business_profile_tax_identifier",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(64))
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)


class BusinessProfileBankAccount(Base):
    __tablename__ = "business_profile_bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    label: Mapped[str] = mapped_column(String(100))
    account_holder: Mapped[str] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    iban: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    routing_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
