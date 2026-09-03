"""Explicit public projections: raw upstream payloads are never returned."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.utc_timestamp import UtcTimestamp


class LexwarePaymentItemRead(BaseModel):
    item_type: str
    category: str
    amount: Decimal
    currency: str
    posting_date: date | None


class LexwareDocumentFinanceRead(BaseModel):
    currency: str
    total_amount: Decimal | None
    open_amount: Decimal | None
    payment_state: Literal["known", "unknown", "not_applicable"]
    payment_status: str | None
    direction: Literal["receivable", "payable", "none"]
    credit: bool
    overdue: bool | None
    included_in_totals: bool
    exclusion_reason: str | None
    payment_items: list[LexwarePaymentItemRead]


class LexwareFileRead(BaseModel):
    file_id: str
    cached: bool
    filename: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    cached_at: UtcTimestamp | None = None


class LexwareDocumentRead(BaseModel):
    id: int
    connection_id: int
    business_profile_id: int
    company_name: str
    source: Literal["lexware"] = "lexware"
    external_id: str
    voucher_type: str
    voucher_status: str
    voucher_number: str | None
    voucher_date: date | None
    contact_name: str | None
    supported: bool
    archived: bool
    in_latest_sync: bool
    connection_enabled: bool
    sync_status: str
    last_success_at: UtcTimestamp | None
    updated_at: UtcTimestamp
    version: int
    local_document_id: int | None
    # These keys are omitted entirely without payments:read.
    due_date: date | None = None
    finance: LexwareDocumentFinanceRead | None = None
    files: list[LexwareFileRead] | None = None


class LexwareDocumentList(BaseModel):
    items: list[LexwareDocumentRead]
    total: int


class LexwareLinkCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_document_id: int | None = Field(ge=1)
    expected_version: int = Field(ge=1)


class LexwareCurrencyTotals(BaseModel):
    currency: str
    receivables: Decimal = Decimal("0.00")
    payables: Decimal = Decimal("0.00")
    overdue_receivables: Decimal = Decimal("0.00")
    overdue_payables: Decimal = Decimal("0.00")
    document_count: int = 0


class LexwareFinanceRead(BaseModel):
    source: Literal["lexware"] = "lexware"
    as_of: date
    totals: list[LexwareCurrencyTotals]
    included_count: int
    linked_count: int
    unknown_count: int
    excluded_count: int
    unsupported_count: int
    stale_connection_count: int
