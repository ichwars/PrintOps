from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

import pycountry
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.core.text_normalization import (
    normalize_case_insensitive_key,
    normalize_tag_name_key,
)

CustomerKind = Literal["company", "person"]
CustomerStatus = Literal["active", "inactive", "blocked"]
CustomerAddressKind = Literal["billing", "delivery", "other"]
TaxValidationStatus = Literal["unchecked", "valid", "invalid"]

_COUNTRY_CODES = frozenset(country.alpha_2 for country in pycountry.countries)
_CURRENCY_CODES = frozenset(currency.alpha_3 for currency in pycountry.currencies)
_TagName = Annotated[str, Field(min_length=1, max_length=100)]
_DISCOUNT_QUANTUM = Decimal("0.01")


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
        raise ValueError("preferred_currency must be a valid ISO 4217 alpha-3 code")
    return normalized


class _NormalizedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_blank_strings(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class CustomerAccountInput(_NormalizedModel):
    business_profile_id: int = Field(gt=0)
    number: str | None = Field(default=None, min_length=1, max_length=50)
    preferred_currency: str = Field(min_length=3, max_length=3)
    payment_term_days: int = Field(default=14, ge=0, le=365)
    delivery_terms: str | None = Field(default=None, max_length=1000)
    discount_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    is_active: bool = True

    @field_validator("preferred_currency")
    @classmethod
    def uppercase_currency_code(cls, value: str) -> str:
        return _normalize_currency_code(value)

    @field_validator("discount_percent")
    @classmethod
    def require_exact_discount_scale(cls, value: Decimal) -> Decimal:
        quantized = value.quantize(_DISCOUNT_QUANTUM)
        if value != quantized:
            raise ValueError("discount_percent must be exactly representable with two decimals")
        return quantized


class CustomerContactInput(_NormalizedModel):
    salutation: str | None = Field(default=None, max_length=32)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    is_primary: bool = False
    include_on_documents: bool = False


class CustomerAddressInput(_NormalizedModel):
    kind: CustomerAddressKind
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


class CustomerTaxIdentifierInput(_NormalizedModel):
    kind: str = Field(min_length=1, max_length=32)
    value: str = Field(min_length=1, max_length=64)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    validation_status: TaxValidationStatus = "unchecked"

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, value: str) -> str:
        normalized = normalize_case_insensitive_key(value)
        if len(normalized) > 32:
            raise ValueError("kind must not exceed 32 characters after normalization")
        return normalized

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str | None) -> str | None:
        return _normalize_country_code(value)


class CustomerCreate(_NormalizedModel):
    kind: CustomerKind
    display_name: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    status: CustomerStatus = "active"
    preferred_locale: str = Field(default="en", min_length=2, max_length=16)
    notes: str | None = Field(default=None, max_length=10000)
    accounts: list[CustomerAccountInput] = Field(min_length=1)
    contacts: list[CustomerContactInput] = Field(default_factory=list)
    addresses: list[CustomerAddressInput] = Field(default_factory=list)
    tax_identifiers: list[CustomerTaxIdentifierInput] = Field(default_factory=list)
    tags: list[_TagName] = Field(default_factory=list, max_length=50)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> object:
        if not isinstance(value, list):
            return value

        normalized: dict[str, object] = {}
        for tag in value:
            if not isinstance(tag, str):
                return value
            display_name = tag.strip()
            if not display_name:
                return value
            key = normalize_tag_name_key(display_name)
            current = normalized.get(key)
            if current is None or display_name < current:
                normalized[key] = display_name
        return sorted(
            normalized.values(),
            key=lambda tag: (normalize_case_insensitive_key(tag), tag),
        )

    @model_validator(mode="after")
    def validate_aggregate(self) -> Self:
        if self.kind == "company" and not self.company_name:
            raise ValueError("company_name is required for company customers")
        if self.kind == "person" and (not self.first_name or not self.last_name):
            raise ValueError("first_name and last_name are required for person customers")

        profile_ids = [account.business_profile_id for account in self.accounts]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("Only one account is allowed per business profile")

        if sum(contact.is_primary for contact in self.contacts) > 1:
            raise ValueError("Only one primary contact is allowed")

        default_address_kinds = [address.kind for address in self.addresses if address.is_default]
        if len(default_address_kinds) != len(set(default_address_kinds)):
            raise ValueError("Only one default address is allowed per kind")

        tax_identifier_keys = [
            (tax_id.kind, normalize_case_insensitive_key(tax_id.value))
            for tax_id in self.tax_identifiers
        ]
        if len(tax_identifier_keys) != len(set(tax_identifier_keys)):
            raise ValueError("Duplicate tax identifiers are not allowed")
        return self


class CustomerUpdate(CustomerCreate):
    version: int = Field(ge=1)


class CustomerAccountResponse(CustomerAccountInput):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int


class CustomerContactResponse(CustomerContactInput):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int


class CustomerAddressResponse(CustomerAddressInput):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int


class CustomerTaxIdentifierResponse(CustomerTaxIdentifierInput):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int


class CustomerDetailResponse(CustomerCreate):
    id: int
    version: int
    created_at: datetime
    updated_at: datetime
    accounts: list[CustomerAccountResponse]
    contacts: list[CustomerContactResponse]
    addresses: list[CustomerAddressResponse]
    tax_identifiers: list[CustomerTaxIdentifierResponse]
    tags: list[str]


class CustomerListItem(_NormalizedModel):
    id: int
    business_profile_id: int
    account_number: str
    preferred_currency: str
    payment_term_days: int
    delivery_terms: str | None
    discount_percent: Decimal
    account_is_active: bool
    display_name: str
    company_name: str | None
    first_name: str | None
    last_name: str | None
    kind: CustomerKind
    status: CustomerStatus
    preferred_locale: str
    primary_contact_name: str | None
    primary_contact_email: str | None
    billing_city: str | None
    billing_country_code: str | None
    tags: list[str]
    version: int


class CustomerListResponse(_NormalizedModel):
    items: list[CustomerListItem]
    total: int
    limit: int
    offset: int
