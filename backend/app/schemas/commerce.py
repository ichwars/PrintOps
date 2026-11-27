from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.commercial_document import CommercialDocumentLineRead
from backend.app.schemas.stock_reservation import ReservationRead

OfferStatus = Literal["draft", "sent", "accepted", "rejected"]


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
    quotation_document_id: int | None = None
    number: str
    status: OfferStatus
    preferred_variant_sort_order: int
    snapshot: dict
    sent_at: datetime | None
    accepted_at: datetime | None
    rejected_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class CommercialAmountsRead(CommerceSchema):
    currency: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    lines: list[CommercialDocumentLineRead]


class OfferQuotationRead(CommercialAmountsRead):
    customer_id: int | None


class OfferListItemRead(OfferRead):
    customer_display_name: str | None = None


class OfferPageQuery(CommerceSchema):
    status: OfferStatus | None = None
    customer_id: int | None = Field(default=None, gt=0, le=2147483647)
    business_profile_id: int | None = Field(default=None, gt=0, le=2147483647)
    calculation_id: int | None = Field(default=None, gt=0, le=2147483647)
    q: str = Field(default="", max_length=200)
    sort_by: Literal["number", "calculation", "customer", "revision", "price", "status", "updated"] = "updated"
    sort_dir: Literal["asc", "desc"] = "desc"
    status_order: list[OfferStatus] = Field(default_factory=list, max_length=4)
    offset: int = Field(default=0, ge=0, le=9007199254740991)
    limit: int = Field(default=25, ge=1, le=200)


class OfferPageRead(CommerceSchema):
    items: list[OfferListItemRead]
    total: int
    offset: int
    limit: int


class OfferDetailRead(OfferListItemRead):
    quotation: OfferQuotationRead | None


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


class OrderDetailRead(OrderRead):
    customer_display_name: str | None
    confirmation: CommercialAmountsRead | None


class AcceptanceRead(CommerceSchema):
    offer: OfferRead
    order: OrderRead
    project_id: int
