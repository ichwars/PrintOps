from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer


class ReservationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_decimals(self, value):
        return str(value) if isinstance(value, Decimal) else value


class AllocationRead(ReservationSchema):
    id: int
    inventory_backend: str
    spool_id: int | None
    external_spool_id: str | None
    small_part_id: int | None
    allocated_quantity: Decimal
    consumed_quantity: Decimal


class ReservationRead(ReservationSchema):
    id: int
    source_key: str
    resource_kind: str
    material_code: str | None
    requested_quantity: Decimal
    unit_code: str
    status: str
    released_at: datetime | None
    allocations: list[AllocationRead]


class AvailabilityAllocationRead(ReservationSchema):
    backend: str
    resource_id: str
    quantity: Decimal


class AvailabilityLineRead(ReservationSchema):
    source_key: str
    resource_kind: str
    description: str | None
    material_code: str | None
    small_part_id: int | None
    unit_code: str
    required: Decimal
    physical: Decimal
    reserved: Decimal
    available: Decimal
    shortage: Decimal
    status: Literal["available", "short", "unmapped"]
    allocations: list[AvailabilityAllocationRead]


class AvailabilityReportRead(ReservationSchema):
    lines: list[AvailabilityLineRead]
    reservation_state: Literal["not_reserved"] = "not_reserved"
    checked_at: datetime
