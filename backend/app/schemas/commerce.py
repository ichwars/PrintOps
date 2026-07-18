from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.stock_reservation import ReservationRead


class CommerceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class OfferCreate(CommerceSchema):
    calculation_revision_id: int = Field(gt=0)


class VersionedTransition(CommerceSchema):
    expected_version: int = Field(gt=0)


class OfferAccept(VersionedTransition):
    idempotency_key: str = Field(min_length=8, max_length=128)


class ReservationCommand(CommerceSchema):
    idempotency_key: str = Field(min_length=8, max_length=128)


class ReservationQuantityCommand(ReservationCommand):
    quantity: Decimal = Field(gt=0)


class OfferRead(CommerceSchema):
    id: int
    business_profile_id: int
    customer_id: int | None
    calculation_revision_id: int
    order_id: int | None = None
    number: str
    status: Literal["draft", "sent", "accepted", "rejected"]
    preferred_variant_sort_order: int
    snapshot: dict
    sent_at: datetime | None
    accepted_at: datetime | None
    rejected_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class OrderRead(CommerceSchema):
    id: int
    business_profile_id: int
    customer_id: int | None
    offer_id: int
    project_id: int
    number: str
    status: Literal["active", "cancelled", "completed"]
    accepted_snapshot: dict
    created_at: datetime
    updated_at: datetime
    reservations: list[ReservationRead]


class AcceptanceRead(CommerceSchema):
    offer: OfferRead
    order: OrderRead
    project_id: int
