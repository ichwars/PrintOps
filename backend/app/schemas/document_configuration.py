"""Strict API and effective-value contracts for document configuration."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
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


class BankAssignmentDraft(StrictModel):
    bank_account_id: int
    is_default: bool = False


class InstallmentDraft(StrictModel):
    percent: Decimal
    due_days: int


class PaymentPolicyDraft(StrictModel):
    payment_term_days: int
    currency: str
    discount_days: int = 0
    discount_percent: Decimal = Decimal("0")
    installments: list[InstallmentDraft] = Field(default_factory=list)
    bank_assignments: list[BankAssignmentDraft] = Field(default_factory=list)


class DunningStageDraft(StrictModel):
    level: int
    wait_days: int
    fee: Decimal = Decimal("0")
    charge_interest: bool = False
    new_due_days: int = 7
    body: str = ""
    escalation_hint: str | None = None


class DunningPolicyDraft(StrictModel):
    enabled: bool = False
    annual_interest_rate: Decimal = Decimal("0")
    flat_fee: Decimal = Decimal("0")
    stages: list[DunningStageDraft] = Field(default_factory=list)


class DocumentTextBlockDraft(StrictModel):
    purpose: str
    body: str
    condition: dict | None = None
    position: int = 0


class DocumentConfigurationDraft(StrictModel):
    document_type: DocumentType
    language: str
    payment: PaymentPolicyDraft
    dunning: DunningPolicyDraft
    text_blocks: list[DocumentTextBlockDraft]


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


class UpdateConfigurationCommand(StrictModel):
    expected_version: int = Field(gt=0)
    patch: dict


class PublishConfigurationRequest(PublishConfigurationCommand):
    pass


class WithdrawConfigurationCommand(StrictModel):
    expected_version: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)


class EffectivePolicyRequest(StrictModel):
    business_profile_id: int = Field(gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    document_type: DocumentType
    language: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$", max_length=16)
    document_overrides: dict = Field(default_factory=dict)


class DocumentConfigurationSummary(StrictModel):
    id: int
    business_profile_id: int
    document_type: str
    language: str
    version: int
    status: str
    effective_from: date | None
    lock_version: int
    change_reason: str | None
    published_at: datetime | None


class DocumentConfigurationDetail(DocumentConfigurationSummary):
    policy: DocumentConfigurationDraft | None
    validation_findings: list[dict] = Field(default_factory=list)


class DocumentCatalogItem(StrictModel):
    key: str
    einvoice: bool
    issuer_role: Literal["seller", "buyer"]
    has_payment_terms: bool
    has_tax: bool
    allowed_successors: list[str]


class DocumentCatalogResponse(StrictModel):
    document_types: list[DocumentCatalogItem]


class PlaceholderCatalogResponse(StrictModel):
    placeholders: list[str]
    text_block_purposes: list[str]
