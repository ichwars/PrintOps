"""Operational readiness aggregation for document configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.business_profile import BusinessProfile, BusinessProfileBankAccount
from backend.app.models.number_sequence import NumberSequence
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, DocumentType
from backend.app.services.document_configuration import load_configuration, to_draft_schema
from backend.app.services.document_policy_validation import PolicyFinding, validate_policy
from backend.app.services.order_errors import InvalidStateConflictError, ResourceNotFoundError

_SEQUENCE_KEYS: dict[DocumentType, str] = {
    DocumentType.QUOTATION: "offer",
    DocumentType.ORDER_CONFIRMATION: "order",
    DocumentType.DELIVERY_NOTE: "order",
    DocumentType.ADVANCE_INVOICE: "invoice",
    DocumentType.PROGRESS_INVOICE: "invoice",
    DocumentType.FINAL_INVOICE: "invoice",
    DocumentType.INVOICE: "invoice",
    DocumentType.CANCELLATION_INVOICE: "invoice",
    DocumentType.INVOICE_CORRECTION: "invoice",
    DocumentType.COMMERCIAL_CREDIT_NOTE: "invoice",
    DocumentType.PAYMENT_REMINDER: "invoice",
    DocumentType.DUNNING_NOTICE: "invoice",
    DocumentType.SELF_BILLING: "invoice",
}


class ReadinessFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["warning", "blocker"]
    code: str
    field_path: str
    message_key: str
    correction: str
    rule_id: str | None = None


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: Literal["configuration", "document"]
    status: Literal["ready", "warnings", "blocked"]
    findings: list[ReadinessFinding]


def report_from_findings(
    context: Literal["configuration", "document"],
    findings: list[ReadinessFinding],
) -> ReadinessReport:
    ordered = sorted(findings, key=lambda item: (item.field_path, item.code))
    if any(item.severity == "blocker" for item in ordered):
        status = "blocked"
    elif ordered:
        status = "warnings"
    else:
        status = "ready"
    return ReadinessReport(context=context, status=status, findings=ordered)


def _from_policy_finding(finding: PolicyFinding) -> ReadinessFinding:
    return ReadinessFinding(
        severity=finding.severity,
        code=finding.code,
        field_path=finding.field_path,
        message_key=finding.message_key,
        correction="Correct the highlighted configuration field",
        rule_id=finding.rule_id,
    )


def _blocker(code: str, field_path: str, message_key: str, correction: str) -> ReadinessFinding:
    return ReadinessFinding(
        severity="blocker",
        code=code,
        field_path=field_path,
        message_key=message_key,
        correction=correction,
    )


async def check_configuration(session: AsyncSession, configuration_id: int) -> ReadinessReport:
    configuration = await load_configuration(session, configuration_id)
    document_type = DocumentType(configuration.document_type)
    capability = DOCUMENT_CAPABILITIES[document_type]
    findings: list[ReadinessFinding] = []

    try:
        findings.extend(_from_policy_finding(item) for item in validate_policy(to_draft_schema(configuration)))
    except InvalidStateConflictError:
        findings.append(
            _blocker(
                "configuration_policy_missing",
                "configuration",
                "documents.errors.configurationPolicyMissing",
                "Create all required policy sections for this document type",
            )
        )

    profile = await session.scalar(
        select(BusinessProfile)
        .where(BusinessProfile.id == configuration.business_profile_id)
        .options(
            selectinload(BusinessProfile.addresses),
            selectinload(BusinessProfile.tax_identifiers),
            selectinload(BusinessProfile.bank_accounts),
        )
    )
    if profile is None:
        raise ResourceNotFoundError(f"Business profile {configuration.business_profile_id} was not found")

    usable_address = next(
        (
            address
            for address in profile.addresses
            if address.kind in {"registered", "billing"}
            and address.street.strip()
            and address.postal_code.strip()
            and address.city.strip()
            and address.country_code.strip()
        ),
        None,
    )
    if usable_address is None:
        findings.append(
            _blocker(
                "seller_address_missing",
                "business_profile.addresses",
                "documents.errors.sellerAddressMissing",
                "Add a complete registered or billing address to the business profile",
            )
        )
    if capability.has_tax and not profile.tax_identifiers:
        findings.append(
            _blocker(
                "seller_tax_identifier_missing",
                "business_profile.tax_identifiers",
                "documents.errors.sellerTaxIdentifierMissing",
                "Add the applicable tax number or VAT identifier",
            )
        )

    payment_policy = configuration.payment_policy
    bank_account = None
    if payment_policy is not None and payment_policy.bank_account_id is not None:
        bank_account = await session.get(BusinessProfileBankAccount, payment_policy.bank_account_id)
    if capability.has_payment_terms and (
        bank_account is None
        or bank_account.business_profile_id != configuration.business_profile_id
        or not bank_account.iban
    ):
        findings.append(
            _blocker(
                "bank_account_missing",
                "payment.bank_account_id",
                "documents.errors.bankAccountMissing",
                "Assign a business-profile bank account with an IBAN",
            )
        )

    sequence_key = _SEQUENCE_KEYS[document_type]
    sequence_exists = await session.scalar(
        select(NumberSequence.id).where(
            NumberSequence.business_profile_id == configuration.business_profile_id,
            NumberSequence.key == sequence_key,
        )
    )
    if sequence_exists is None:
        findings.append(
            _blocker(
                "number_sequence_missing",
                "number_sequence",
                "documents.errors.numberSequenceMissing",
                f"Configure the {sequence_key} number sequence for this business profile",
            )
        )

    if capability.einvoice:
        einvoice = configuration.einvoice_policy
        if einvoice is None:
            findings.append(
                _blocker(
                    "einvoice_policy_missing",
                    "einvoice",
                    "documents.errors.einvoicePolicyMissing",
                    "Create the E-invoice policy for this document type",
                )
            )
        else:
            if einvoice.en16931_version != "1.3.16" or einvoice.cius_version != "3.0.2":
                findings.append(
                    _blocker(
                        "einvoice_ruleset_unavailable",
                        "einvoice.ruleset",
                        "documents.errors.einvoiceRulesetUnavailable",
                        "Select EN 16931 1.3.16 and XRechnung 3.0.2",
                    )
                )
            if not einvoice.seller_identifier:
                findings.append(
                    _blocker(
                        "seller_endpoint_missing",
                        "einvoice.seller_identifier",
                        "documents.errors.sellerEndpointMissing",
                        "Enter the seller electronic-address identifier and scheme",
                    )
                )
            if einvoice.syntax not in {"ubl_2_1", "cii"}:
                findings.append(
                    _blocker(
                        "einvoice_syntax_invalid",
                        "einvoice.syntax",
                        "documents.errors.einvoiceSyntaxInvalid",
                        "Select UBL 2.1 or UN/CEFACT CII",
                    )
                )
            if einvoice.zugferd_profile not in {"EN16931", "XRECHNUNG"}:
                findings.append(
                    _blocker(
                        "zugferd_profile_invalid",
                        "einvoice.zugferd_profile",
                        "documents.errors.zugferdProfileInvalid",
                        "Select EN16931 or XRECHNUNG",
                    )
                )

    return report_from_findings("configuration", findings)
