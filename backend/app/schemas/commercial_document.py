from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

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


class UpdateCommercialDocumentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    document: CommercialDocumentDraft


class VersionedDocumentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)


class IssueDocumentCommand(VersionedDocumentCommand):
    idempotency_key: str = Field(min_length=8, max_length=128)


class SuccessorDocumentCommand(VersionedDocumentCommand):
    successor_type: str = Field(min_length=1, max_length=32)
    relation_type: str = Field(default="successor", min_length=1, max_length=32)


class ReasonedDocumentCommand(VersionedDocumentCommand):
    reason: str = Field(min_length=1, max_length=2000)


class TaxOverrideDocumentCommand(ReasonedDocumentCommand):
    tax_decision: dict[str, Any]


class CommercialDocumentLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    description: str
    quantity: Decimal
    unit_code: str
    unit_price: Decimal
    net_amount: Decimal
    tax_category_code: str
    tax_rate: Decimal
    product_identifier: str | None


class CommercialDocumentArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    content_type: str
    sha256: str
    validation_status: str
    rule_versions: dict[str, Any]
    original_role: Literal["original", "visual_copy", "component"] = "component"
    layout_configuration_id: int | None = None
    layout_version: int | None = None
    layout_effective_sha256: str | None = None
    renderer_version: str | None = None
    validator_version: str | None = None
    export_manifest: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CommercialDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_type: str
    business_profile_id: int
    customer_id: int | None
    number: str | None
    external_issuer_number: str | None
    technical_status: str
    business_status: str
    payment_status: str
    issue_date: date | None
    service_date: date | None
    due_date: date | None
    language: str
    currency: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    open_amount: Decimal
    content_options: dict[str, Any]
    tax_decision: dict[str, Any]
    lock_version: int
    created_at: datetime
    updated_at: datetime
    lines: list[CommercialDocumentLineRead]
    artifacts: list[CommercialDocumentArtifactRead]
    snapshot_sha256: str | None = None


class DocumentAuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    object_type: str
    object_id: int
    actor_id: int | None
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    correlation_id: str
    created_at: datetime
