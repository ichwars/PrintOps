from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pycountry
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.core.text_normalization import normalize_case_insensitive_key

_COUNTRY_CODES = frozenset(country.alpha_2 for country in pycountry.countries)
_CURRENCY_CODES = frozenset(currency.alpha_3 for currency in pycountry.currencies)


def _normalize_country_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper()
    if normalized not in _COUNTRY_CODES:
        raise ValueError("country_code must be a valid ISO 3166-1 alpha-2 code")
    return normalized


def _normalize_currency_code(value: str) -> str:
    normalized = value.upper()
    if normalized not in _CURRENCY_CODES:
        raise ValueError("currency must be a valid ISO 4217 alpha-3 code")
    return normalized


class _NormalizedModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_blank_strings(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class BusinessProfileAddress(_NormalizedModel):
    kind: Literal["registered", "billing", "shipping", "other"]
    label: str | None = Field(default=None, max_length=100)
    additional: str | None = Field(default=None, max_length=255)
    street: str = Field(min_length=1, max_length=255)
    street_2: str | None = Field(default=None, max_length=255)
    postal_code: str = Field(min_length=1, max_length=32)
    city: str = Field(min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country_code: str = Field(min_length=2, max_length=2)
    is_default: bool = False

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str) -> str:
        normalized = _normalize_country_code(value)
        assert normalized is not None
        return normalized


class BusinessProfileTaxIdentifier(_NormalizedModel):
    kind: str = Field(min_length=1, max_length=32)
    value: str = Field(min_length=1, max_length=64)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    is_primary: bool = False
    valid_from: date | None = None
    valid_until: date | None = None

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str | None) -> str | None:
        return _normalize_country_code(value)

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, value: str) -> str:
        normalized = normalize_case_insensitive_key(value)
        if len(normalized) > 32:
            raise ValueError("kind must not exceed 32 characters after normalization")
        return normalized

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.valid_from is not None and self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be on or after valid_from")
        return self


class BusinessProfileBankAccount(_NormalizedModel):
    label: str = Field(min_length=1, max_length=100)
    account_holder: str = Field(min_length=1, max_length=255)
    bank_name: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    currency: str = Field(min_length=3, max_length=3)
    iban: str | None = Field(default=None, max_length=64)
    bic: str | None = Field(default=None, max_length=32)
    account_number: str | None = Field(default=None, max_length=64)
    routing_number: str | None = Field(default=None, max_length=64)
    is_default: bool = False

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str | None) -> str | None:
        return _normalize_country_code(value)

    @field_validator("currency")
    @classmethod
    def uppercase_currency_code(cls, value: str) -> str:
        return _normalize_currency_code(value)

    @model_validator(mode="after")
    def require_account_identifier(self) -> Self:
        if not self.iban and not self.account_number:
            raise ValueError("Either iban or account_number is required")
        return self


class BusinessProfileCreate(_NormalizedModel):
    name: str = Field(min_length=1, max_length=100)
    legal_name: str = Field(min_length=1, max_length=255)
    trading_name: str | None = Field(default=None, max_length=255)
    country_code: str = Field(min_length=2, max_length=2)
    default_currency: str = Field(min_length=3, max_length=3)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    default_locale: str = Field(default="en", min_length=1, max_length=16)
    billing_mode: Literal["internal", "external", "hybrid"] = "hybrid"
    tax_mode: Literal["standard", "exempt", "none"] = "standard"
    default_tax_rate: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, decimal_places=2)
    cash_accounting: bool = False
    input_tax_deductible: bool = True
    show_offer_qr: bool = False
    paypal_me_url: str | None = Field(default=None, max_length=500)
    is_active: bool = True
    is_default: bool = False
    addresses: list[BusinessProfileAddress]
    tax_identifiers: list[BusinessProfileTaxIdentifier] = Field(default_factory=list)
    bank_accounts: list[BusinessProfileBankAccount] = Field(default_factory=list)

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str) -> str:
        normalized = _normalize_country_code(value)
        assert normalized is not None
        return normalized

    @field_validator("default_currency")
    @classmethod
    def uppercase_currency_code(cls, value: str) -> str:
        return _normalize_currency_code(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @field_validator("paypal_me_url")
    @classmethod
    def validate_paypal_me_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname not in {"paypal.me", "www.paypal.me"}:
            raise ValueError("paypal_me_url must be an HTTPS paypal.me URL")
        if parsed.username or parsed.password or parsed.port is not None:
            raise ValueError("paypal_me_url must not contain credentials or a port")
        return value

    @model_validator(mode="after")
    def validate_nested_defaults(self) -> Self:
        if self.tax_mode in {"exempt", "none"}:
            self.default_tax_rate = Decimal("0.00")
            self.input_tax_deductible = False

        if not any(address.kind == "registered" for address in self.addresses):
            raise ValueError("At least one registered address is required")

        default_address_kinds = [address.kind for address in self.addresses if address.is_default]
        if len(default_address_kinds) != len(set(default_address_kinds)):
            raise ValueError("Only one default address is allowed per kind")

        primary_tax_kinds = [tax_id.kind for tax_id in self.tax_identifiers if tax_id.is_primary]
        if len(primary_tax_kinds) != len(set(primary_tax_kinds)):
            raise ValueError("Only one primary tax identifier is allowed per kind")

        tax_identifier_keys = [
            (tax_id.kind, normalize_case_insensitive_key(tax_id.value)) for tax_id in self.tax_identifiers
        ]
        if len(tax_identifier_keys) != len(set(tax_identifier_keys)):
            raise ValueError("Duplicate tax identifiers are not allowed")

        default_bank_currencies = [account.currency for account in self.bank_accounts if account.is_default]
        if len(default_bank_currencies) != len(set(default_bank_currencies)):
            raise ValueError("Only one default bank account is allowed per currency")
        return self


class BusinessProfileUpdate(BusinessProfileCreate):
    version: int = Field(ge=1)


class BusinessProfileAddressResponse(BusinessProfileAddress):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int


class BusinessProfileTaxIdentifierResponse(BusinessProfileTaxIdentifier):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int


class BusinessProfileBankAccountResponse(BusinessProfileBankAccount):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int


class BusinessProfileResponse(BusinessProfileCreate):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int
    version: int
    created_at: datetime
    updated_at: datetime
    logo_media_type: str | None = None
    logo_version: int | None = None
    addresses: list[BusinessProfileAddressResponse]
    tax_identifiers: list[BusinessProfileTaxIdentifierResponse]
    bank_accounts: list[BusinessProfileBankAccountResponse]


class BusinessProfileOption(_NormalizedModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int
    name: str
    country_code: str
    default_currency: str
    timezone: str
    default_locale: str
    billing_mode: Literal["internal", "external", "hybrid"]
    is_default: bool
    is_active: bool
