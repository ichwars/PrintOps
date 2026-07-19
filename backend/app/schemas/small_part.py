from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from backend.app.schemas.procurement import ProcurementOfferRead


class SmallPartSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_decimals(self, value):
        return str(value) if isinstance(value, Decimal) else value


class SmallPartCategoryCreate(SmallPartSchema):
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True


class SmallPartCategoryUpdate(SmallPartSchema):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None


class SmallPartCategoryRead(SmallPartSchema):
    id: int
    name: str
    is_active: bool


class SmallPartUnitCreate(SmallPartSchema):
    code: str = Field(min_length=1, max_length=16)
    label: str = Field(min_length=1, max_length=80)
    decimal_places: int = Field(default=0, ge=0, le=6)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class SmallPartUnitUpdate(SmallPartSchema):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    decimal_places: int | None = Field(default=None, ge=0, le=6)
    is_active: bool | None = None


class SmallPartUnitRead(SmallPartSchema):
    code: str
    label: str
    decimal_places: int
    is_active: bool


class SmallPartBase(SmallPartSchema):
    sku: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    search_terms: str | None = None
    category_id: int | None = Field(default=None, gt=0)
    unit_code: str = Field(min_length=1, max_length=16)
    location_id: int | None = Field(default=None, gt=0)
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0)
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)
    supplier_reference: str | None = Field(default=None, max_length=255)
    default_consumption_reason: str = Field(default="Produktion", min_length=1, max_length=120)
    internal_notes: str | None = None
    is_active: bool = True

    @field_validator("unit_code")
    @classmethod
    def normalize_unit_code(cls, value: str) -> str:
        return value.strip().upper()


class SmallPartCreate(SmallPartBase):
    opening_quantity: Decimal = Field(default=Decimal("0"), ge=0)


class SmallPartUpdate(SmallPartSchema):
    sku: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    search_terms: str | None = None
    category_id: int | None = Field(default=None, gt=0)
    unit_code: str | None = Field(default=None, min_length=1, max_length=16)
    location_id: int | None = Field(default=None, gt=0)
    minimum_stock: Decimal | None = Field(default=None, ge=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    supplier_reference: str | None = Field(default=None, max_length=255)
    default_consumption_reason: str | None = Field(default=None, min_length=1, max_length=120)
    internal_notes: str | None = None
    is_active: bool | None = None

    @field_validator("unit_code")
    @classmethod
    def normalize_unit_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class SmallPartBalanceRead(SmallPartSchema):
    physical: Decimal
    reserved: Decimal
    available: Decimal
    is_low_stock: bool


class SmallPartRead(SmallPartBase):
    id: int
    preferred_offer: ProcurementOfferRead | None = None
    category: SmallPartCategoryRead | None = None
    unit: SmallPartUnitRead
    balance: SmallPartBalanceRead
    created_at: datetime
    updated_at: datetime


class SmallPartLedgerCreate(SmallPartSchema):
    entry_kind: Literal["receipt", "correction"]
    quantity: Decimal
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_quantity(self) -> Self:
        if self.entry_kind == "receipt" and self.quantity <= 0:
            raise ValueError("receipt quantity must be positive")
        if self.entry_kind == "correction" and self.quantity == 0:
            raise ValueError("correction quantity must be non-zero")
        return self


class SmallPartLedgerRead(SmallPartSchema):
    id: int
    small_part_id: int
    entry_kind: str
    physical_delta: Decimal
    reserved_delta: Decimal
    reason: str
    reference_type: str | None
    reference_id: int | None
    actor_id: int | None
    idempotency_key: str
    created_at: datetime


class SmallPartOptionRead(SmallPartSchema):
    id: int
    sku: str
    name: str
    unit_code: str
    unit_cost: Decimal
    available: Decimal


class SmallPartListResponse(SmallPartSchema):
    items: list[SmallPartRead]
    total: int
    limit: int
    offset: int
