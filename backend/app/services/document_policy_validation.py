"""Deterministic validation and rendering for document policies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

import pycountry

from backend.app.schemas.document_configuration import DocumentConfigurationDraft, DocumentTextBlockDraft
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, PLACEHOLDERS, TEXT_BLOCK_PURPOSES, DocumentType

_PLACEHOLDER_PATTERN = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
_ALL_DOCUMENT_TYPES = frozenset(DocumentType)
_PLACEHOLDER_DOCUMENT_TYPES: dict[str, frozenset[DocumentType]] = {
    "DOCUMENT_NUMBER": _ALL_DOCUMENT_TYPES,
    "VALID_UNTIL": frozenset({DocumentType.QUOTATION}),
    "QUOTATION_VALID_UNTIL": frozenset({DocumentType.QUOTATION}),
    "ORDER_REFERENCE": frozenset(
        {
            DocumentType.ORDER_CONFIRMATION,
            DocumentType.ADVANCE_INVOICE,
            DocumentType.PROGRESS_INVOICE,
            DocumentType.FINAL_INVOICE,
            DocumentType.INVOICE,
        }
    ),
    "DUE_DATE": frozenset(
        document_type
        for document_type, capability in DOCUMENT_CAPABILITIES.items()
        if capability.has_payment_terms
    ),
    "SERVICE_DATE": frozenset({DocumentType.PROGRESS_INVOICE, DocumentType.FINAL_INVOICE, DocumentType.INVOICE}),
    "ORIGINAL_DOCUMENT_NUMBER": frozenset(
        {
            DocumentType.CANCELLATION_INVOICE,
            DocumentType.INVOICE_CORRECTION,
            DocumentType.PAYMENT_REMINDER,
            DocumentType.DUNNING_NOTICE,
        }
    ),
    "OPEN_AMOUNT": frozenset({DocumentType.PAYMENT_REMINDER, DocumentType.DUNNING_NOTICE}),
    "CURRENCY": frozenset({DocumentType.PAYMENT_REMINDER, DocumentType.DUNNING_NOTICE}),
    "DUNNING_LEVEL": frozenset({DocumentType.DUNNING_NOTICE}),
}
_KNOWN_PLACEHOLDERS = frozenset(item for item in PLACEHOLDERS if item.isupper()) | frozenset(
    _PLACEHOLDER_DOCUMENT_TYPES
)


@dataclass(frozen=True, slots=True)
class PolicyFinding:
    severity: Literal["warning", "blocker"]
    code: str
    field_path: str
    message_key: str
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class RenderedTextBlock:
    purpose: str
    body: str
    position: int


class ConfigurationNotReady(RuntimeError):
    def __init__(self, findings: tuple[PolicyFinding, ...]):
        self.findings = findings
        super().__init__("Document configuration contains publication blockers")


def _finding(code: str, field_path: str, message_key: str, *, rule_id: str | None = None) -> PolicyFinding:
    return PolicyFinding("blocker", code, field_path, message_key, rule_id)


def _validate_placeholders(
    document_type: DocumentType,
    blocks: list[DocumentTextBlockDraft],
) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    for index, block in enumerate(blocks):
        for placeholder in sorted(set(_PLACEHOLDER_PATTERN.findall(block.body))):
            field_path = f"text_blocks.{index}.body"
            if placeholder not in _KNOWN_PLACEHOLDERS:
                findings.append(
                    _finding(
                        "placeholder_unknown",
                        field_path,
                        "documents.errors.placeholderUnknown",
                    )
                )
                continue
            available_types = _PLACEHOLDER_DOCUMENT_TYPES.get(placeholder, _ALL_DOCUMENT_TYPES)
            if document_type not in available_types:
                findings.append(
                    _finding(
                        "placeholder_not_available",
                        field_path,
                        "documents.errors.placeholderNotAvailable",
                    )
                )
    return findings


def validate_policy(policy: DocumentConfigurationDraft) -> tuple[PolicyFinding, ...]:
    findings: list[PolicyFinding] = []
    payment = policy.payment
    dunning = policy.dunning

    if payment.payment_term_days < 0:
        findings.append(
            _finding("payment_term_negative", "payment.payment_term_days", "documents.errors.paymentTermNegative")
        )
    if payment.discount_days < 0:
        findings.append(_finding("discount_days_negative", "payment.discount_days", "documents.errors.discountDaysNegative"))
    if payment.discount_percent < 0:
        findings.append(
            _finding("discount_percent_negative", "payment.discount_percent", "documents.errors.discountPercentNegative")
        )
    if payment.discount_percent > 0 and payment.discount_days > payment.payment_term_days:
        findings.append(
            _finding(
                "discount_after_due_date",
                "payment.discount_days",
                "documents.errors.discountAfterDue",
            )
        )
    if payment.installments:
        total = sum((item.percent for item in payment.installments), Decimal("0"))
        if total != Decimal("100"):
            findings.append(
                _finding(
                    "installments_total_invalid",
                    "payment.installments",
                    "documents.errors.installmentsTotal",
                )
            )
        for index, installment in enumerate(payment.installments):
            if installment.percent <= 0:
                findings.append(
                    _finding(
                        "installment_percent_invalid",
                        f"payment.installments.{index}.percent",
                        "documents.errors.installmentPercent",
                    )
                )
            if installment.due_days < 0:
                findings.append(
                    _finding(
                        "installment_due_days_negative",
                        f"payment.installments.{index}.due_days",
                        "documents.errors.installmentDueDays",
                    )
                )

    currency = payment.currency.upper()
    if pycountry.currencies.get(alpha_3=currency) is None:
        findings.append(_finding("currency_invalid", "payment.currency", "documents.errors.currencyInvalid"))
    language_code = policy.language.split("-", 1)[0].lower()
    if len(language_code) != 2 or pycountry.languages.get(alpha_2=language_code) is None:
        findings.append(_finding("language_invalid", "language", "documents.errors.languageInvalid"))

    if dunning.annual_interest_rate < 0:
        findings.append(
            _finding(
                "dunning_interest_negative",
                "dunning.annual_interest_rate",
                "documents.errors.dunningInterestNegative",
            )
        )
    if dunning.flat_fee < 0:
        findings.append(_finding("dunning_fee_negative", "dunning.flat_fee", "documents.errors.dunningFeeNegative"))
    levels = [stage.level for stage in dunning.stages]
    if len(levels) != len(set(levels)):
        findings.append(
            _finding(
                "dunning_stage_level_duplicate",
                "dunning.stages",
                "documents.errors.dunningStageDuplicate",
            )
        )
    if levels and levels != list(range(1, len(levels) + 1)):
        findings.append(
            _finding(
                "dunning_stage_order_invalid",
                "dunning.stages",
                "documents.errors.dunningStageOrder",
            )
        )
    for index, stage in enumerate(dunning.stages):
        if stage.fee < 0:
            findings.append(
                _finding(
                    "dunning_stage_fee_negative",
                    f"dunning.stages.{index}.fee",
                    "documents.errors.dunningStageFeeNegative",
                )
            )
        if stage.wait_days < 0 or stage.new_due_days < 0:
            findings.append(
                _finding(
                    "dunning_stage_days_negative",
                    f"dunning.stages.{index}",
                    "documents.errors.dunningStageDaysNegative",
                )
            )

    purposes = [block.purpose for block in policy.text_blocks]
    for purpose in purposes:
        if purpose not in TEXT_BLOCK_PURPOSES:
            findings.append(_finding("text_purpose_invalid", "text_blocks", "documents.errors.textPurposeInvalid"))
    if len(purposes) != len(set(purposes)):
        findings.append(_finding("text_purpose_duplicate", "text_blocks", "documents.errors.textPurposeDuplicate"))
    required_purposes = {"intro", "closing"}
    if DOCUMENT_CAPABILITIES[policy.document_type].has_payment_terms:
        required_purposes.add("payment_terms")
    for purpose in sorted(required_purposes):
        matching = [block for block in policy.text_blocks if block.purpose == purpose and block.body.strip()]
        if not matching:
            findings.append(
                _finding(
                    "required_text_missing",
                    f"text_blocks.{purpose}",
                    "documents.errors.requiredTextMissing",
                )
            )
    findings.extend(_validate_placeholders(policy.document_type, policy.text_blocks))

    if DOCUMENT_CAPABILITIES[policy.document_type].has_payment_terms:
        default_count = sum(assignment.is_default for assignment in payment.bank_assignments)
        if default_count == 0:
            findings.append(
                _finding("default_bank_missing", "payment.bank_assignments", "documents.errors.defaultBankMissing")
            )
        elif default_count > 1:
            findings.append(
                _finding("default_bank_multiple", "payment.bank_assignments", "documents.errors.defaultBankMultiple")
            )
        account_ids = [assignment.bank_account_id for assignment in payment.bank_assignments]
        if len(account_ids) != len(set(account_ids)):
            findings.append(
                _finding("bank_assignment_duplicate", "payment.bank_assignments", "documents.errors.bankDuplicate")
            )

    return tuple(sorted(findings, key=lambda item: (item.field_path, item.code)))


def render_text_blocks(
    blocks: list[DocumentTextBlockDraft],
    values: dict[str, str],
    document_type: DocumentType | str,
) -> tuple[RenderedTextBlock, ...]:
    normalized_type = DocumentType(document_type)
    placeholder_findings = _validate_placeholders(normalized_type, blocks)
    missing_findings: list[PolicyFinding] = []
    rendered: list[RenderedTextBlock] = []
    for index, block in enumerate(sorted(blocks, key=lambda item: item.position)):
        def replace(match: re.Match[str], block_index: int = index) -> str:
            placeholder = match.group(1)
            if placeholder not in values:
                missing_findings.append(
                    _finding(
                        "placeholder_value_missing",
                        f"text_blocks.{block_index}.body",
                        "documents.errors.placeholderValueMissing",
                    )
                )
                return match.group(0)
            return str(values[placeholder])

        rendered.append(RenderedTextBlock(block.purpose, _PLACEHOLDER_PATTERN.sub(replace, block.body), block.position))
    findings = tuple(sorted([*placeholder_findings, *missing_findings], key=lambda item: (item.field_path, item.code)))
    if findings:
        raise ConfigurationNotReady(findings)
    return tuple(rendered)
