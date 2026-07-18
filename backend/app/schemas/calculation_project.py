from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class CalculationProjectSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_decimals(self, value):
        return str(value) if isinstance(value, Decimal) else value


class CalculationVariantPlateInput(CalculationProjectSchema):
    project_plate_id: int = Field(gt=0)
    good_parts: int = Field(default=1, ge=0)
    parts_per_print: int = Field(default=1, gt=0)
    scrap_prints: int = Field(default=0, ge=0)
    material_code: str | None = Field(default=None, max_length=120)
    grams_per_print: Decimal | None = Field(default=None, ge=0)
    hours_per_print: Decimal | None = Field(default=None, ge=0)
    overrides: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=0)


class CalculationVariantPlateRead(CalculationVariantPlateInput):
    id: int
    plate_name: str
    plate_index: int
    stable_key: str


class CalculationVariantSmallPartInput(CalculationProjectSchema):
    small_part_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    description_snapshot: str = Field(min_length=1, max_length=255)
    unit_code_snapshot: str = Field(min_length=1, max_length=16)
    unit_cost_snapshot: Decimal = Field(ge=0)
    sort_order: int = Field(default=0, ge=0)


class CalculationVariantSmallPartRead(CalculationVariantSmallPartInput):
    id: int
    sku: str
    available: Decimal | None = None


class CalculationProjectPlateRead(CalculationProjectSchema):
    id: int
    plate_index: int
    stable_key: str
    name: str
    object_count: int
    detected_materials: list
    detected_grams: Decimal | None
    detected_hours: Decimal | None
    geometry: dict
    thumbnail_url: str | None = None


class CalculationProjectFileRead(CalculationProjectSchema):
    id: int
    calculation_id: int
    revision_number: int
    original_filename: str
    sha256: str
    size_bytes: int
    analysis_status: Literal["pending", "completed", "failed"]
    analysis_error: str | None
    printer_metadata: dict
    created_at: datetime
    plates: list[CalculationProjectPlateRead]


class CalculationSliceRequest(CalculationProjectSchema):
    plate_ids: list[int] = Field(min_length=1)
    printer_preset: dict | None = None
    process_preset: dict | None = None
    filament_preset: dict | None = None
    allow_estimate_fallback: bool = True
