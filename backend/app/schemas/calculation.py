from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

import pycountry
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

CalculationStatus = Literal["draft", "approved", "superseded", "archived"]
PriceMethod = Literal["markup", "target_margin", "explicit_price"]
AllocationBasis = Literal["request", "run", "unit"]
LineKind = Literal["printed_part", "service", "material", "packaging", "shipping", "discount", "text"]
OperationKind = Literal["cad", "slicing", "setup", "printing", "drying", "post_processing", "qa", "packing"]

_CURRENCIES = frozenset(currency.alpha_3 for currency in pycountry.currencies)


class CalculationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_decimals(self, value):
        return str(value) if isinstance(value, Decimal) else value


class CalculationLaborInput(CalculationSchema):
    kind: str = Field(min_length=1, max_length=24)
    hours: Decimal = Field(ge=0)
    hourly_rate: Decimal = Field(ge=0)
    allocation_basis: AllocationBasis = "request"
    sort_order: int = Field(default=0, ge=0)


class CalculationOperationInput(CalculationSchema):
    kind: OperationKind
    title: str = Field(min_length=1, max_length=255)
    source_file: str | None = Field(default=None, max_length=500)
    source_plate: int | None = Field(default=None, ge=0)
    good_parts: int = Field(default=1, ge=0)
    parts_per_run: int = Field(default=1, gt=0)
    scrap_runs: int = Field(default=0, ge=0)
    material_grams_per_run: Decimal = Field(default=Decimal("0"), ge=0)
    print_hours_per_run: Decimal = Field(default=Decimal("0"), ge=0)
    provenance: dict = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=0)
    labor: list[CalculationLaborInput] = Field(default_factory=list)


class CalculationLineInput(CalculationSchema):
    kind: LineKind
    description: str = Field(min_length=1, max_length=10000)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_code: str = Field(default="C62", min_length=1, max_length=16)
    unit_price: Decimal | None = Field(default=None, ge=0)
    sort_order: int = Field(default=0, ge=0)


class CalculationVariantInput(CalculationSchema):
    name: str = Field(min_length=1, max_length=120)
    is_preferred: bool = False
    sort_order: int = Field(default=0, ge=0)
    price_method: PriceMethod = "target_margin"
    price_rate: Decimal = Field(default=Decimal("0"), ge=0)
    lines: list[CalculationLineInput] = Field(default_factory=list)
    operations: list[CalculationOperationInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_margin(self) -> Self:
        if self.price_method == "target_margin" and self.price_rate >= 1:
            raise ValueError("target margin must be below one")
        return self


class CalculationCreate(CalculationSchema):
    business_profile_id: int = Field(gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=255)
    currency: str = Field(min_length=3, max_length=3)
    notes: str | None = Field(default=None, max_length=10000)
    variants: list[CalculationVariantInput] = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if value not in _CURRENCIES:
            raise ValueError("currency must be a valid ISO 4217 alpha-3 code")
        return value

    @model_validator(mode="after")
    def validate_preferred_variant(self) -> Self:
        if sum(item.is_preferred for item in self.variants) != 1:
            raise ValueError("exactly one preferred variant is required")
        return self


class CalculationUpdate(CalculationCreate):
    expected_version: int = Field(gt=0)


class CalculationApprove(CalculationSchema):
    expected_version: int = Field(gt=0)
    warning_reasons: dict[str, str] = Field(default_factory=dict)


class CalculationTemplateCreate(CalculationSchema):
    name: str = Field(min_length=1, max_length=255)
    revision_id: int | None = Field(default=None, gt=0)


class CalculationPreviewInput(CalculationSchema):
    good_parts: int = Field(default=1, ge=0)
    parts_per_run: int = Field(default=1, gt=0)
    scrap_runs: int = Field(default=0, ge=0)
    material_grams_per_run: Decimal = Field(default=Decimal("0"), ge=0)
    material_price_per_kg: Decimal = Field(default=Decimal("0"), ge=0)
    print_hours_per_run: Decimal = Field(default=Decimal("0"), ge=0)
    machine_cost_per_hour: Decimal = Field(default=Decimal("0"), ge=0)
    acquisition_value: Decimal | None = Field(default=None, ge=0)
    residual_value: Decimal = Field(default=Decimal("0"), ge=0)
    service_years: Decimal | None = Field(default=None, gt=0)
    annual_hours: Decimal | None = Field(default=None, gt=0)
    maintenance_rate: Decimal = Field(default=Decimal("0"), ge=0)
    printer_power_kw: Decimal = Field(default=Decimal("0"), ge=0)
    electricity_price_per_kwh: Decimal = Field(default=Decimal("0"), ge=0)
    drying_hours: Decimal = Field(default=Decimal("0"), ge=0)
    dryer_power_kw: Decimal = Field(default=Decimal("0"), ge=0)
    labor: list[CalculationLaborInput] = Field(default_factory=list)
    consumables: Decimal = Field(default=Decimal("0"), ge=0)
    packaging: Decimal = Field(default=Decimal("0"), ge=0)
    additional_costs: Decimal = Field(default=Decimal("0"), ge=0)
    risk_rate: Decimal = Field(default=Decimal("0"), ge=0)
    shipping: Decimal = Field(default=Decimal("0"), ge=0)
    price_method: PriceMethod = "target_margin"
    price_rate: Decimal = Field(default=Decimal("0"), ge=0)
    explicit_price: Decimal = Field(default=Decimal("0"), ge=0)
    discount_rate: Decimal = Field(default=Decimal("0"), ge=0, lt=1)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_price: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_profit: Decimal = Field(default=Decimal("0"), ge=0)
    rounding_mode: Literal["none", "0.05", "0.10", "0.50", "1.00", "x.90", "x.99"] = "none"


class CalculationPreviewRead(CalculationSchema):
    total_runs: int
    material_cost: Decimal
    machine_cost: Decimal
    energy_cost: Decimal
    labor_cost: Decimal
    consumables: Decimal
    packaging: Decimal
    additional_costs: Decimal
    risk_cost: Decimal
    production_cost: Decimal
    shipping: Decimal
    selling_price: Decimal
    net_price: Decimal
    contribution: Decimal
    effective_margin: Decimal
    tax: Decimal
    gross_price: Decimal
    unit_price: Decimal


class CalculationDetail(CalculationSchema):
    id: int
    business_profile_id: int
    customer_id: int | None
    title: str
    status: CalculationStatus
    currency: str
    notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    variants: list[CalculationVariantInput]
    current_revision: int | None = None
    production_cost: Decimal | None = None
    selling_price: Decimal | None = None


class CalculationListResponse(CalculationSchema):
    items: list[CalculationDetail]
    total: int
    limit: int
    offset: int


class CalculationRevisionRead(CalculationSchema):
    id: int
    calculation_id: int
    revision_number: int
    snapshot: dict
    production_cost: Decimal
    selling_price: Decimal
    currency: str
    approved_by_id: int | None
    approved_at: datetime


class CalculationTemplateRead(CalculationSchema):
    id: int
    business_profile_id: int
    name: str
    version: int
    definition: dict
    created_at: datetime
