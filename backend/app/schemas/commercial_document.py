from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CommercialDocumentLineDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    position: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=2000)
    quantity: Decimal
    unit_code: str = Field(min_length=1, max_length=16)
    unit_price: Decimal
    net_amount: Decimal
    tax_category_code: str = Field(min_length=1, max_length=8)
    tax_rate: Decimal = Field(ge=0, le=100)
    product_identifier: str | None = Field(default=None, max_length=255)
    source_data: dict[str, Any] = Field(default_factory=dict)
    internal_calculation: dict[str, Any] = Field(default_factory=dict)


class CommercialDocumentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    document_type: str = Field(min_length=1, max_length=32)
    business_profile_id: int = Field(gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    external_issuer_number: str | None = Field(default=None, max_length=100)
    issue_date: date | None = None
    service_date: date | None = None
    due_date: date | None = None
    language: str = Field(min_length=2, max_length=16)
    currency: str = Field(min_length=3, max_length=3)
    lines: tuple[CommercialDocumentLineDraft, ...] = ()
    content_options: dict[str, Any] = Field(default_factory=dict)
    tax_decision: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_draft_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def require_unique_line_positions(self) -> CommercialDocumentDraft:
        positions = [line.position for line in self.lines]
        if len(positions) != len(set(positions)):
            raise ValueError("Commercial document line positions must be unique")
        return self


class SnapshotLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    position: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=2000)
    quantity: Decimal
    unit_code: str = Field(min_length=1, max_length=16)
    unit_price: Decimal
    net_amount: Decimal
    tax_category_code: str = Field(min_length=1, max_length=8)
    tax_rate: Decimal
    product_identifier: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IssuedDocumentSnapshot(BaseModel):
    """Immutable semantic payload frozen at the instant of issuance."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    document_type: str = Field(min_length=1, max_length=32)
    number: str = Field(min_length=1, max_length=100)
    issue_date: date
    service_date: date | None = None
    due_date: date | None = None
    language: str = Field(min_length=2, max_length=16)
    currency: str = Field(min_length=3, max_length=3)
    seller: dict[str, Any]
    buyer: dict[str, Any]
    lines: tuple[SnapshotLine, ...] = Field(min_length=1)
    totals: dict[str, Decimal]
    payment: dict[str, Any] = Field(default_factory=dict)
    references: tuple[dict[str, Any], ...] = ()
    text_blocks: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()
