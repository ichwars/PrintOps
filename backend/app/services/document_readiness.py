"""Operational readiness aggregation for document configuration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from importlib import resources
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.models.business_profile import BusinessProfile, BusinessProfileBankAccount
from backend.app.models.number_sequence import NumberSequence
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, DocumentType
from backend.app.services.document_configuration import load_configuration, to_draft_schema
from backend.app.services.document_policy_validation import PolicyFinding, validate_policy
from backend.app.services.order_errors import InvalidStateConflictError, ResourceNotFoundError
from backend.app.services.verapdf import VeraPdfExecutionError, VeraPdfRunner, VeraPdfUnavailable

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


class RuntimeComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    version: str | None = None


class DocumentRuntimeReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ready: bool
    renderer: RuntimeComponent
    pango: RuntimeComponent
    icc_profile_sha256: str | None
    icc_profile_valid: bool
    validator: RuntimeComponent
    findings: tuple[str, ...]


def probe_document_runtime(
    *,
    renderer_cli: Path | None = None,
    validator: VeraPdfRunner | None = None,
    process_runner: Callable = subprocess.run,
) -> DocumentRuntimeReadiness:
    """Return version-only operational data; configured filesystem paths stay private."""
    findings: list[str] = []
    renderer_version = None
    pango_version = None
    cli = Path(renderer_cli) if renderer_cli is not None else None
    if cli is None or not cli.is_file():
        findings.extend(("PDF_RENDERER_UNAVAILABLE", "PDF_PANGO_UNAVAILABLE"))
    else:
        try:
            result = process_runner(
                [str(cli), "--info"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            output = f"{result.stdout}\n{result.stderr}"
            renderer_match = re.search(r"WeasyPrint version:\s*([^\s]+)", output)
            pango_match = re.search(r"Pango version:\s*([^\s]+)", output)
            if result.returncode == 0 and renderer_match:
                renderer_version = renderer_match.group(1)
                pango_version = pango_match.group(1) if pango_match else None
            else:
                findings.append("PDF_RENDERER_UNAVAILABLE")
            if pango_version is None:
                findings.append("PDF_PANGO_UNAVAILABLE")
        except (OSError, subprocess.TimeoutExpired):
            findings.extend(("PDF_RENDERER_UNAVAILABLE", "PDF_PANGO_UNAVAILABLE"))

    manifest = json.loads(
        resources.files("backend.app.resources.pdf").joinpath("runtime-manifest.json").read_text(encoding="utf-8")
    )
    icc = resources.files("backend.app.resources.pdf").joinpath(manifest["srgb"]["filename"])
    icc_digest = hashlib.sha256(icc.read_bytes()).hexdigest() if icc.is_file() else None
    icc_valid = icc_digest == manifest["srgb"]["sha256"]
    if not icc_valid:
        findings.append("PDF_ICC_PROFILE_INVALID")

    active_validator = validator or VeraPdfRunner(
        cli_path=settings.verapdf_cli,
        report_dir=settings.document_validation_report_dir,
        timeout_seconds=settings.document_validation_timeout_seconds,
    )
    try:
        validator_version = active_validator.version()
    except (VeraPdfUnavailable, VeraPdfExecutionError):
        validator_version = None
        findings.append("PDF_VALIDATOR_UNAVAILABLE")
    unique_findings = tuple(dict.fromkeys(findings))
    return DocumentRuntimeReadiness(
        ready=not unique_findings,
        renderer=RuntimeComponent(available=renderer_version is not None, version=renderer_version),
        pango=RuntimeComponent(available=pango_version is not None, version=pango_version),
        icc_profile_sha256=icc_digest,
        icc_profile_valid=icc_valid,
        validator=RuntimeComponent(
            available=validator_version is not None,
            version=validator_version,
        ),
        findings=unique_findings,
    )


def _configured_runtime_blockers() -> list[ReadinessFinding]:
    if settings.weasyprint_cli is None and settings.verapdf_cli is None:
        return []
    status = probe_document_runtime(renderer_cli=settings.weasyprint_cli)
    return [
        _blocker(
            code.lower(),
            "runtime.pdf",
            f"documents.errors.{code.lower()}",
            "Installierte PDF-Laufzeit prüfen oder Anwendungspaket reparieren",
        )
        for code in status.findings
    ]


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
    findings.extend(_configured_runtime_blockers())

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


async def check_issuance_readiness(
    session: AsyncSession,
    configuration_id: int,
    *,
    business_profile_id: int,
    document_type: str,
    language: str,
    issue_date: date,
) -> ReadinessReport:
    """Aggregate every prerequisite that must pass before reserving a number."""
    base = await check_configuration(session, configuration_id)
    findings = list(base.findings)
    runtime = probe_document_runtime(renderer_cli=settings.weasyprint_cli)
    existing_codes = {item.code for item in findings}
    for code in runtime.findings:
        normalized = code.lower()
        if normalized not in existing_codes:
            findings.append(
                _blocker(
                    normalized,
                    "runtime.pdf",
                    f"documents.errors.{normalized}",
                    "Install or repair the pinned PDF renderer and validator runtime",
                )
            )
    from backend.app.models.document_layout import DocumentLayoutConfiguration
    from backend.app.services.document_layout_assets import AssetError, read_asset
    from backend.app.services.document_layouts import resolve_effective_layout

    effective_at = datetime.combine(issue_date, time.max, tzinfo=UTC)
    try:
        resolved = await resolve_effective_layout(
            session,
            business_profile_id=business_profile_id,
            document_type=document_type,
            language="de" if language.lower().startswith("de") else "en",
            now=effective_at,
        )
        layouts = list(
            await session.scalars(
                select(DocumentLayoutConfiguration).where(
                    DocumentLayoutConfiguration.id.in_(resolved.configuration_ids)
                )
            )
        )
        if not any(item.document_type is None and item.language is None for item in layouts):
            findings.append(
                _blocker(
                    "published_layout_missing",
                    "layout_resolution",
                    "documents.errors.publishedLayoutMissing",
                    "Publish a profile-default document layout before issuing",
                )
            )
        for layout in layouts:
            for link in layout.asset_links:
                try:
                    if link.asset.preflight_status != "valid":
                        raise AssetError("asset preflight is not valid")
                    read_asset(link.asset)
                except (AssetError, OSError):
                    findings.append(
                        _blocker(
                            "layout_asset_invalid",
                            f"layout.assets.{link.role}",
                            "documents.errors.layoutAssetInvalid",
                            "Replace or revalidate the referenced layout asset",
                        )
                    )
    except (LookupError, ValueError, RuntimeError):
        findings.append(
            _blocker(
                "layout_resolution_failed",
                "layout_resolution",
                "documents.errors.layoutResolutionFailed",
                "Publish a valid layout for this profile, document type and language",
            )
        )
    return report_from_findings("document", findings)
