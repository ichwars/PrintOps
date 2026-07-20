"""Strict API and effective-value contracts for document configuration."""

from __future__ import annotations

from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.document_catalog import DocumentType

T = TypeVar("T")
ValueSource = Literal["system", "business_profile", "customer", "configuration", "document"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourcedValue(StrictModel, Generic[T]):
    value: T
    source: ValueSource
    overridable: bool


class CreateConfigurationCommand(StrictModel):
    business_profile_id: int = Field(gt=0)
    document_type: DocumentType
    language: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$", max_length=16)
    change_reason: str | None = Field(default=None, min_length=3, max_length=1000)


class PublishConfigurationCommand(StrictModel):
    expected_version: int = Field(gt=0)
    effective_from: date
    reason: str = Field(min_length=3, max_length=1000)


class EffectiveBasicPolicy(StrictModel):
    subject: SourcedValue[str]
    validity_days: SourcedValue[int | None]
    date_rule: SourcedValue[str]
    rounding_mode: SourcedValue[str]


class EffectivePaymentPolicy(StrictModel):
    payment_term_days: SourcedValue[int]
    currency: SourcedValue[str]
    due_date_basis: SourcedValue[str]
    payment_methods: SourcedValue[list[str]]
    early_payment_rules: SourcedValue[list[dict]]
    prepayment_percent: SourcedValue[str]
    installment_enabled: SourcedValue[bool]
    bank_account_id: SourcedValue[int | None]
    use_term_in_invoice_text: SourcedValue[bool]


class EffectiveContentPolicy(StrictModel):
    include_calculation_data: SourcedValue[bool]
    visible_content: SourcedValue[dict]


class EffectiveTaxPolicy(StrictModel):
    allowed_cases: SourcedValue[list[str]]
    decision_rules: SourcedValue[dict]
    allow_override: SourcedValue[bool]


class EffectiveEInvoicePolicy(StrictModel):
    requirement: SourcedValue[str]
    en16931_version: SourcedValue[str]
    cius_name: SourcedValue[str]
    cius_version: SourcedValue[str]
    syntax: SourcedValue[str]
    zugferd_profile: SourcedValue[str]
    process_identifier: SourcedValue[str | None]
    seller_identifier: SourcedValue[str | None]
    seller_identifier_scheme: SourcedValue[str | None]
    default_payment_method: SourcedValue[str | None]
    bank_account_id: SourcedValue[int | None]
    recipient_requirements: SourcedValue[dict]


class EffectiveTextBlock(StrictModel):
    purpose: str
    body: SourcedValue[str]
    condition: dict | None = None
    position: int


class EffectiveDocumentPolicy(StrictModel):
    configuration_id: int
    configuration_version: int
    basic: EffectiveBasicPolicy
    payment: EffectivePaymentPolicy
    content: EffectiveContentPolicy
    tax: EffectiveTaxPolicy
    einvoice: EffectiveEInvoicePolicy
    text_blocks: list[EffectiveTextBlock]
