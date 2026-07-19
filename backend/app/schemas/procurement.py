from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class ProcurementSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_decimals(self, value):
        return str(value) if isinstance(value, Decimal) else value


class SupplierBase(ProcurementSchema):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    website: str | None = Field(default=None, max_length=2048)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    customer_number: str | None = Field(default=None, max_length=120)
    payment_terms: str | None = Field(default=None, max_length=500)
    default_lead_time_days: int = Field(default=0, ge=0, le=3650)
    internal_notes: str | None = None
    is_active: bool = True

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str | None) -> str | None:
        return value.upper() if value else value


def supplier_name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(ProcurementSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    website: str | None = Field(default=None, max_length=2048)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    customer_number: str | None = Field(default=None, max_length=120)
    payment_terms: str | None = Field(default=None, max_length=500)
    default_lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    internal_notes: str | None = None
    is_active: bool | None = None

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class SupplierRead(SupplierBase):
    id: int
    created_at: datetime
    updated_at: datetime


class SupplierListResponse(ProcurementSchema):
    items: list[SupplierRead]
    total: int
    limit: int
    offset: int
