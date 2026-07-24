from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import (
    CommercialDocument,
    CommercialDocumentLine,
    DocumentNumberReservation,
    DocumentRelation,
)
from backend.app.models.customer import Customer, CustomerAccount
from backend.app.models.document_configuration import DocumentConfiguration
from backend.app.schemas.commercial_document import (
    CommercialDocumentDraft,
    CommercialDocumentLineDraft,
    IssuedDocumentSnapshot,
    SnapshotLine,
)
from backend.app.services.document_audit import append_audit
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, DocumentType
from backend.app.services.document_numbering import reserve_document_number
from backend.app.services.document_readiness import check_issuance_readiness
from backend.app.services.document_snapshot import attach_issued_snapshot, render_issued_pdf
from backend.app.services.einvoice.artifacts import store_artifact
from backend.app.services.einvoice.canonical import from_snapshot, validate_math
from backend.app.services.einvoice.validator import (
    EInvoiceValidationReport,
    validate_xml,
)
from backend.app.services.einvoice.xrechnung import render_xrechnung
from backend.app.services.einvoice.zugferd import render_zugferd
from backend.app.services.order_errors import ResourceInUseError, ResourceNotFoundError, VersionConflictError


class InvalidDocumentTransition(ResourceInUseError):
    pass


class DocumentValidationFailed(ResourceInUseError):
    def __init__(self, findings: tuple[DocumentFinding, ...]):
        super().__init__("The commercial document is not ready")
        self.findings = findings


class EInvoiceValidationFailed(ResourceInUseError):
    failure_code = "einvoice_invalid"


class IssuanceConflict(ResourceInUseError):
    pass


@dataclass(frozen=True, slots=True)
class GeneratedArtifact:
    kind: str
    content_type: str
    content: bytes
    sha256: str
    report: EInvoiceValidationReport

    @property
    def validation_status(self) -> str:
        return "valid" if self.report.valid else "invalid"

    @property
    def validation_report(self) -> dict:
        return self.report.to_dict()

    @property
    def rule_versions(self) -> dict:
        return dict(self.report.rule_versions)


async def generate_required_artifact(
    session: AsyncSession,
    document: CommercialDocument,
    snapshot: IssuedDocumentSnapshot,
) -> GeneratedArtifact | None:
    """Render and officially validate the E-invoice required by the frozen snapshot."""
    del session
    policy = dict(snapshot.metadata.get("einvoice") or {})
    if document.customer_id is None or not policy.get("required"):
        return None

    standard = str(policy.get("standard") or "xrechnung").lower()
    syntax = str(policy.get("syntax") or "ubl_2_1").lower()
    profile = str(policy.get("profile") or "xrechnung").lower()
    try:
        invoice = from_snapshot(snapshot)
        math_findings = validate_math(invoice)
        if math_findings:
            details = ", ".join(f"{item.code} ({item.path})" for item in math_findings)
            raise EInvoiceValidationFailed(f"E-invoice totals are inconsistent: {details}")

        if standard == "xrechnung":
            if syntax in {"ubl", "ubl_2_1", "ubl-2.1"}:
                renderer_syntax = "ubl"
            elif syntax in {"cii", "cii_d16b", "cii-d16b"}:
                renderer_syntax = "cii"
            else:
                raise ValueError(f"Unsupported XRechnung syntax {syntax!r}")
            normalized_syntax = "ubl-2.1" if renderer_syntax == "ubl" else "cii-d16b"
            xml = render_xrechnung(invoice, renderer_syntax)
            kind = "xrechnung_xml"
            profile = "xrechnung"
        elif standard == "zugferd":
            if profile not in {"en16931", "xrechnung"}:
                raise ValueError(f"Unsupported ZUGFeRD profile {profile!r}")
            xml = render_zugferd(invoice, profile)
            normalized_syntax = "cii-d22b"
            kind = "zugferd_xml"
        else:
            raise ValueError(f"Unsupported E-invoice standard {standard!r}")
    except EInvoiceValidationFailed:
        raise
    except (TypeError, ValueError) as exc:
        raise EInvoiceValidationFailed(f"E-invoice source data is incomplete: {exc}") from exc

    report = validate_xml(
        xml,
        standard=standard,
        syntax=normalized_syntax,
        profile=profile,
    )
    if not report.valid:
        detail = report.processing_error or "; ".join(
            f"{item.rule_id} {item.field_path}: {item.message}" for item in report.blockers[:10]
        )
        raise EInvoiceValidationFailed(f"Generated electronic invoice is invalid: {detail}")
    return GeneratedArtifact(
        kind=kind,
        content_type="application/xml",
        content=xml,
        sha256=sha256(xml).hexdigest(),
        report=report,
    )


@dataclass(frozen=True, slots=True)
class DocumentFinding:
    severity: Literal["warning", "blocker"]
    code: str
    field_path: str
    message: str


TECHNICAL_TRANSITIONS = {
    "draft": frozenset({"validation_failed", "ready"}),
    "validation_failed": frozenset({"draft", "ready"}),
    "ready": frozenset({"draft", "issued"}),
    "issued": frozenset({"cancelled", "corrected", "replaced"}),
    "cancelled": frozenset(),
    "corrected": frozenset(),
    "replaced": frozenset(),
}

_LOAD_OPTIONS = (
    selectinload(CommercialDocument.lines),
    selectinload(CommercialDocument.incoming_relations),
    selectinload(CommercialDocument.outgoing_relations),
    selectinload(CommercialDocument.snapshot),
    selectinload(CommercialDocument.artifacts),
)


def _finding(code: str, field_path: str, message: str) -> DocumentFinding:
    return DocumentFinding("blocker", code, field_path, message)


def _tax_group(item: dict) -> tuple[str, Decimal]:
    return (
        str(item.get("tax_category_code") or ""),
        Decimal(str(item.get("tax_rate") or "0")),
    )


def _deduction_findings(draft: CommercialDocumentDraft) -> list[DocumentFinding]:
    prior = draft.content_options.get("prior_invoices") or []
    deductions = draft.content_options.get("prior_payment_deductions") or []
    prior_by_group: dict[tuple[str, Decimal], Decimal] = {}
    deduction_by_group: dict[tuple[str, Decimal], Decimal] = {}
    for item in prior:
        group = _tax_group(item)
        prior_by_group[group] = prior_by_group.get(group, Decimal("0")) + Decimal(str(item.get("gross") or "0"))
    for item in deductions:
        group = _tax_group(item)
        deduction_by_group[group] = deduction_by_group.get(group, Decimal("0")) + Decimal(str(item.get("gross") or "0"))

    findings: list[DocumentFinding] = []
    for group, amount in prior_by_group.items():
        if deduction_by_group.get(group) != amount:
            findings.append(
                _finding(
                    "prior_payment_deduction_missing",
                    "content_options.prior_payment_deductions",
                    f"Prior invoice deduction is incomplete for tax group {group[0]} {group[1]}",
                )
            )
    for group in deduction_by_group.keys() - prior_by_group.keys():
        findings.append(
            _finding(
                "prior_payment_deduction_unmatched",
                "content_options.prior_payment_deductions",
                f"Deduction has no prior invoice in tax group {group[0]} {group[1]}",
            )
        )
    return findings


def validate_document(draft: CommercialDocumentDraft) -> tuple[DocumentFinding, ...]:
    findings: list[DocumentFinding] = []
    try:
        document_type = DocumentType(draft.document_type)
    except ValueError:
        return (
            _finding(
                "document_type_unknown",
                "document_type",
                f"Unsupported commercial document type {draft.document_type!r}",
            ),
        )

    options = draft.content_options
    if options.get("include_internal_calculation"):
        findings.append(
            _finding(
                "internal_calculation_forbidden",
                "content_options.include_internal_calculation",
                "Internal calculations must never appear in an external document",
            )
        )
    if document_type == DocumentType.DELIVERY_NOTE and options.get("show_prices"):
        findings.append(
            _finding(
                "delivery_prices_forbidden",
                "content_options.show_prices",
                "Delivery note prices require an explicit future policy and are disabled",
            )
        )
    if document_type == DocumentType.FINAL_INVOICE:
        findings.extend(_deduction_findings(draft))

    if document_type in {DocumentType.PAYMENT_REMINDER, DocumentType.DUNNING_NOTICE}:
        if not options.get("invoice_document_id"):
            findings.append(
                _finding(
                    "reminder_invoice_reference_missing",
                    "content_options.invoice_document_id",
                    "Reminder and dunning documents require the source invoice balance",
                )
            )
        if any(line.tax_rate != 0 or line.tax_category_code not in {"O", "E"} for line in draft.lines):
            findings.append(
                _finding(
                    "reminder_vat_forbidden",
                    "lines",
                    "Reminder and dunning amounts do not add VAT",
                )
            )

    if document_type == DocumentType.SELF_BILLING:
        if not draft.external_issuer_number:
            findings.append(
                _finding(
                    "self_billing_external_number_missing",
                    "external_issuer_number",
                    "Self-billing requires the buyer-issued external number",
                )
            )
        if options.get("issuer_role") != "buyer":
            findings.append(
                _finding(
                    "self_billing_issuer_role_invalid",
                    "content_options.issuer_role",
                    "Self-billing must use the buyer as issuer",
                )
            )

    relation_required = {
        DocumentType.CANCELLATION_INVOICE,
        DocumentType.INVOICE_CORRECTION,
        DocumentType.COMMERCIAL_CREDIT_NOTE,
    }
    if document_type in relation_required and not options.get("original_document_id"):
        findings.append(
            _finding(
                "original_document_reference_missing",
                "content_options.original_document_id",
                "The corrective document must reference its original document",
            )
        )

    if document_type not in {DocumentType.PAYMENT_REMINDER, DocumentType.DUNNING_NOTICE} and not draft.lines:
        findings.append(_finding("document_lines_missing", "lines", "At least one document line is required"))
    return tuple(sorted(findings, key=lambda item: (item.field_path, item.code)))


def _line_from_draft(line: CommercialDocumentLineDraft) -> CommercialDocumentLine:
    return CommercialDocumentLine(**line.model_dump())


def _amounts(lines: tuple[CommercialDocumentLineDraft, ...]) -> tuple[Decimal, Decimal, Decimal]:
    subtotal = sum((line.net_amount for line in lines), Decimal("0.00"))
    tax = sum(
        (line.net_amount * line.tax_rate / Decimal("100") for line in lines),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    return subtotal, tax, subtotal + tax


async def _load_document(
    session: AsyncSession,
    document_id: int,
    *,
    lock: bool = False,
) -> CommercialDocument:
    statement = select(CommercialDocument).where(CommercialDocument.id == document_id).options(*_LOAD_OPTIONS)
    if lock:
        statement = statement.with_for_update()
    document = await session.scalar(statement)
    if document is None:
        raise ResourceNotFoundError(f"Commercial document {document_id} was not found")
    return document


def _to_draft(document: CommercialDocument) -> CommercialDocumentDraft:
    return CommercialDocumentDraft(
        document_type=document.document_type,
        business_profile_id=document.business_profile_id,
        customer_id=document.customer_id,
        external_issuer_number=document.external_issuer_number,
        issue_date=document.issue_date,
        service_date=document.service_date,
        due_date=document.due_date,
        language=document.language,
        currency=document.currency,
        content_options=document.content_options or {},
        tax_decision=document.tax_decision or {},
        lines=tuple(
            CommercialDocumentLineDraft(
                position=line.position,
                description=line.description,
                quantity=line.quantity,
                unit_code=line.unit_code,
                unit_price=line.unit_price,
                net_amount=line.net_amount,
                tax_category_code=line.tax_category_code,
                tax_rate=line.tax_rate,
                product_identifier=line.product_identifier,
                source_data=line.source_data or {},
                internal_calculation=line.internal_calculation or {},
            )
            for line in document.lines
        ),
    )


async def create_draft(
    session: AsyncSession,
    data: CommercialDocumentDraft,
    *,
    actor_id: int | None,
) -> CommercialDocument:
    subtotal, tax, total = _amounts(data.lines)
    document = CommercialDocument(
        **data.model_dump(exclude={"lines"}),
        technical_status="draft",
        payment_status=(
            "unpaid" if DOCUMENT_CAPABILITIES[DocumentType(data.document_type)].has_payment_terms else "not_applicable"
        ),
        subtotal_amount=subtotal,
        tax_amount=tax,
        total_amount=total,
        open_amount=total,
        created_by_id=actor_id,
    )
    document.lines = [_line_from_draft(line) for line in data.lines]
    session.add(document)
    await session.flush()
    return document


async def update_draft(
    session: AsyncSession,
    document_id: int,
    expected_version: int,
    data: CommercialDocumentDraft,
) -> CommercialDocument:
    document = await _load_document(session, document_id, lock=True)
    if document.lock_version != expected_version:
        raise VersionConflictError(f"Commercial document {document_id} has changed")
    if document.technical_status not in {"draft", "validation_failed", "ready"}:
        raise InvalidDocumentTransition("Issued document content cannot be updated")
    if document.business_profile_id != data.business_profile_id:
        raise ValueError("The business profile of a document cannot be changed")

    for field, value in data.model_dump(exclude={"lines", "business_profile_id"}).items():
        setattr(document, field, value)
    existing_lines = {line.position: line for line in document.lines}
    requested_positions = {line.position for line in data.lines}
    for line in list(document.lines):
        if line.position not in requested_positions:
            document.lines.remove(line)
    for line_data in data.lines:
        line = existing_lines.get(line_data.position)
        if line is None:
            document.lines.append(_line_from_draft(line_data))
            continue
        for field, value in line_data.model_dump().items():
            setattr(line, field, value)
    subtotal, tax, total = _amounts(data.lines)
    document.subtotal_amount = subtotal
    document.tax_amount = tax
    document.total_amount = total
    document.open_amount = total
    document.technical_status = "draft"
    document.lock_version += 1
    await session.flush()
    return document


async def validate_draft(
    session: AsyncSession,
    document_id: int,
) -> tuple[DocumentFinding, ...]:
    return validate_document(_to_draft(await _load_document(session, document_id)))


async def transition_document(
    session: AsyncSession,
    document: CommercialDocument,
    target: str,
) -> CommercialDocument:
    if target not in TECHNICAL_TRANSITIONS.get(document.technical_status, frozenset()):
        raise InvalidDocumentTransition(
            f"Commercial document cannot transition from {document.technical_status} to {target}"
        )
    document.technical_status = target
    document.lock_version += 1
    await session.flush()
    return document


async def mark_ready(
    session: AsyncSession,
    document_id: int,
    expected_version: int,
) -> CommercialDocument:
    document = await _load_document(session, document_id, lock=True)
    if document.lock_version != expected_version:
        raise VersionConflictError(f"Commercial document {document_id} has changed")
    findings = validate_document(_to_draft(document))
    blockers = tuple(item for item in findings if item.severity == "blocker")
    if blockers:
        if document.technical_status != "validation_failed":
            await transition_document(session, document, "validation_failed")
        raise DocumentValidationFailed(blockers)
    return await transition_document(session, document, "ready")


async def create_successor(
    session: AsyncSession,
    source_document_id: int,
    successor_type: str,
    *,
    actor_id: int | None,
    relation_type: str = "successor",
) -> CommercialDocument:
    source = await _load_document(session, source_document_id, lock=True)
    source_type = DocumentType(source.document_type)
    try:
        target_type = DocumentType(successor_type)
    except ValueError as exc:
        raise ValueError(f"Unknown successor document type {successor_type!r}") from exc
    if target_type not in DOCUMENT_CAPABILITIES[source_type].allowed_successors:
        raise ValueError(f"{target_type.value} is not an allowed successor of {source_type.value}")
    if source.technical_status != "issued":
        raise InvalidDocumentTransition("Only issued documents can create successors")

    content_options = {"original_document_id": source.id}
    if target_type == DocumentType.SELF_BILLING:
        content_options["issuer_role"] = "buyer"
    successor = CommercialDocument(
        document_type=target_type.value,
        business_profile_id=source.business_profile_id,
        customer_id=source.customer_id,
        technical_status="draft",
        language=source.language,
        currency=source.currency,
        service_date=source.service_date,
        due_date=source.due_date,
        subtotal_amount=source.subtotal_amount,
        tax_amount=source.tax_amount,
        total_amount=source.total_amount,
        open_amount=source.open_amount,
        content_options=content_options,
        tax_decision=dict(source.tax_decision or {}),
        created_by_id=actor_id,
    )
    successor.lines = [
        CommercialDocumentLine(
            position=line.position,
            description=line.description,
            quantity=line.quantity,
            unit_code=line.unit_code,
            unit_price=line.unit_price,
            net_amount=line.net_amount,
            tax_category_code=line.tax_category_code,
            tax_rate=line.tax_rate,
            product_identifier=line.product_identifier,
            source_data=dict(line.source_data or {}),
            internal_calculation=dict(line.internal_calculation or {}),
        )
        for line in source.lines
    ]
    successor.incoming_relations = [DocumentRelation(source_document_id=source.id, relation_type=relation_type)]
    session.add(successor)
    await session.flush()
    return successor


async def cancel_document(
    session: AsyncSession,
    document_id: int,
    *,
    reason: str,
    actor_id: int | None,
) -> CommercialDocument:
    original = await _load_document(session, document_id, lock=True)
    cancellation = await create_successor(
        session,
        document_id,
        DocumentType.CANCELLATION_INVOICE.value,
        actor_id=actor_id,
        relation_type="cancellation",
    )
    for line in cancellation.lines:
        line.quantity = -line.quantity
        line.net_amount = -line.net_amount
    cancellation.subtotal_amount = -original.subtotal_amount
    cancellation.tax_amount = -original.tax_amount
    cancellation.total_amount = -original.total_amount
    cancellation.open_amount = -original.open_amount
    await transition_document(session, original, "cancelled")
    await append_audit(
        session,
        action="cancel",
        object_type="commercial_document",
        object_id=original.id,
        actor_id=actor_id,
        reason=reason,
        before={"technical_status": "issued"},
        after={"technical_status": "cancelled", "successor_id": cancellation.id},
        correlation_id=f"document-cancel-{original.id}-{cancellation.id}",
    )
    return cancellation


async def correct_document(
    session: AsyncSession,
    document_id: int,
    *,
    reason: str,
    actor_id: int | None,
) -> CommercialDocument:
    original = await _load_document(session, document_id, lock=True)
    correction = await create_successor(
        session,
        document_id,
        DocumentType.INVOICE_CORRECTION.value,
        actor_id=actor_id,
        relation_type="correction",
    )
    await transition_document(session, original, "corrected")
    await append_audit(
        session,
        action="correct",
        object_type="commercial_document",
        object_id=original.id,
        actor_id=actor_id,
        reason=reason,
        before={"technical_status": "issued"},
        after={"technical_status": "corrected", "successor_id": correction.id},
        correlation_id=f"document-correct-{original.id}-{correction.id}",
    )
    return correction


@dataclass(frozen=True, slots=True)
class _IssuanceContext:
    configuration_id: int
    configuration_version: int
    tax_rule_version: str
    einvoice_rule_versions: dict[str, str]
    intent_sha256: str
    issue_date: date


def _document_intent_sha256(document: CommercialDocument) -> str:
    payload = _to_draft(document).model_dump(mode="json")
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


async def _issuance_configuration(
    session: AsyncSession,
    document: CommercialDocument,
) -> DocumentConfiguration | None:
    base = select(DocumentConfiguration).where(
        DocumentConfiguration.business_profile_id == document.business_profile_id,
        DocumentConfiguration.document_type == document.document_type,
        DocumentConfiguration.language == document.language,
    )
    if document.issue_date is not None:
        active = await session.scalar(
            base.where(
                DocumentConfiguration.status == "active",
                DocumentConfiguration.effective_from <= document.issue_date,
            ).order_by(
                DocumentConfiguration.effective_from.desc(),
                DocumentConfiguration.version.desc(),
            )
        )
        if active is not None:
            return active
    return await session.scalar(
        base.where(DocumentConfiguration.status == "draft").order_by(DocumentConfiguration.version.desc())
    )


async def _prepare_issuance(
    session: AsyncSession,
    document_id: int,
    expected_version: int,
) -> _IssuanceContext:
    document = await _load_document(session, document_id)
    if document.technical_status == "issued":
        raise IssuanceConflict(f"Commercial document {document_id} is already issued")
    if document.technical_status != "ready":
        raise InvalidDocumentTransition("Only ready commercial documents can be issued")
    if document.lock_version != expected_version:
        raise VersionConflictError(f"Commercial document {document_id} has changed")
    if document.issue_date is None:
        raise DocumentValidationFailed((_finding("issue_date_missing", "issue_date", "An issue date is required"),))
    document_findings = tuple(
        finding for finding in validate_document(_to_draft(document)) if finding.severity == "blocker"
    )
    if document_findings:
        raise DocumentValidationFailed(document_findings)

    configuration = await _issuance_configuration(session, document)
    if configuration is None:
        raise DocumentValidationFailed(
            (
                _finding(
                    "configuration_missing",
                    "configuration",
                    "No effective document configuration exists",
                ),
            )
        )
    readiness = await check_issuance_readiness(
        session,
        configuration.id,
        business_profile_id=document.business_profile_id,
        document_type=document.document_type,
        language=document.language,
        issue_date=document.issue_date,
    )
    blockers = tuple(
        _finding(item.code, item.field_path, item.correction)
        for item in readiness.findings
        if item.severity == "blocker"
    )
    if blockers:
        raise DocumentValidationFailed(blockers)

    einvoice = configuration.einvoice_policy
    einvoice_versions = {}
    if einvoice is not None:
        einvoice_versions = {
            "en16931": einvoice.en16931_version,
            "cius": einvoice.cius_version,
            "cius_name": einvoice.cius_name,
        }
    return _IssuanceContext(
        configuration_id=configuration.id,
        configuration_version=configuration.version,
        tax_rule_version=str((document.tax_decision or {}).get("rule_version") or "2026.1"),
        einvoice_rule_versions=einvoice_versions,
        intent_sha256=_document_intent_sha256(document),
        issue_date=document.issue_date,
    )


def _evidence_sessions(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    if session.bind is None:
        raise RuntimeError("Issuance session has no database bind")
    return async_sessionmaker(session.bind, expire_on_commit=False)


def _assert_reservation_binding(
    reservation: DocumentNumberReservation,
    *,
    document_id: int,
    intent_sha256: str,
) -> None:
    if reservation.document_id != document_id:
        raise IssuanceConflict("The idempotency key belongs to a different document")
    if reservation.intent_sha256 != intent_sha256:
        raise IssuanceConflict("The idempotency key belongs to a different document intent")


async def _existing_reservation(
    session: AsyncSession,
    idempotency_key: str,
) -> DocumentNumberReservation | None:
    return await session.scalar(
        select(DocumentNumberReservation).where(DocumentNumberReservation.idempotency_key == idempotency_key)
    )


async def _reserve_issue_evidence(
    session: AsyncSession,
    *,
    document_id: int,
    effective_date: date,
    idempotency_key: str,
    intent_sha256: str,
) -> tuple[DocumentNumberReservation, bool]:
    sessions = _evidence_sessions(session)
    async with sessions() as evidence_session:
        existing = await _existing_reservation(evidence_session, idempotency_key)
        if existing is not None:
            _assert_reservation_binding(
                existing,
                document_id=document_id,
                intent_sha256=intent_sha256,
            )
            return existing, False
        evidence_document = await evidence_session.get(CommercialDocument, document_id)
        if evidence_document is None:
            raise ResourceNotFoundError(f"Commercial document {document_id} was not found")
        try:
            reservation = await reserve_document_number(
                evidence_session,
                evidence_document,
                effective_date,
                idempotency_key=idempotency_key,
                intent_sha256=intent_sha256,
            )
            await evidence_session.flush()
            await evidence_session.commit()
            return reservation, True
        except IntegrityError:
            await evidence_session.rollback()
            existing = await _existing_reservation(evidence_session, idempotency_key)
            if existing is None:
                raise
            _assert_reservation_binding(
                existing,
                document_id=document_id,
                intent_sha256=intent_sha256,
            )
            return existing, False


async def _mark_reservation(
    session: AsyncSession,
    reservation_id: int,
    status: Literal["consumed", "voided"],
    *,
    failure_code: str | None = None,
    failure_detail: str | None = None,
) -> None:
    sessions = _evidence_sessions(session)
    async with sessions() as evidence_session:
        reservation = await evidence_session.get(DocumentNumberReservation, reservation_id)
        if reservation is None:
            raise ResourceNotFoundError(f"Document number reservation {reservation_id} was not found")
        reservation.status = status
        reservation.failure_code = failure_code
        reservation.failure_detail = failure_detail[:2000] if failure_detail else None
        reservation.finalized_at = datetime.now(UTC)
        await evidence_session.commit()


async def _wait_for_issue_replay(
    session: AsyncSession,
    reservation_id: int,
) -> None:
    sessions = _evidence_sessions(session)
    for _attempt in range(200):
        async with sessions() as evidence_session:
            reservation = await evidence_session.get(DocumentNumberReservation, reservation_id)
            if reservation is None:
                raise ResourceNotFoundError(f"Document number reservation {reservation_id} was not found")
            if reservation.status == "consumed":
                return
            if reservation.status == "voided":
                raise IssuanceConflict(
                    f"The prior issuance attempt failed with {reservation.failure_code or 'unknown'}"
                )
            document_status = await evidence_session.scalar(
                select(CommercialDocument.technical_status).where(CommercialDocument.id == reservation.document_id)
            )
            if document_status == "issued":
                reservation.status = "consumed"
                reservation.finalized_at = datetime.now(UTC)
                await evidence_session.commit()
                return
        await asyncio.sleep(0.025)
    raise IssuanceConflict("The concurrent issuance attempt did not complete in time")


async def _reload_issued_document(
    session: AsyncSession,
    document_id: int,
) -> CommercialDocument:
    statement = (
        select(CommercialDocument)
        .where(CommercialDocument.id == document_id)
        .options(*_LOAD_OPTIONS)
        .execution_options(populate_existing=True)
    )
    document = await session.scalar(statement)
    if document is None:
        raise ResourceNotFoundError(f"Commercial document {document_id} was not found")
    if document.technical_status != "issued" or document.snapshot is None:
        raise IssuanceConflict("Idempotent issuance evidence is incomplete")
    return document


async def _lock_ready_document(
    session: AsyncSession,
    document_id: int,
    expected_version: int,
) -> CommercialDocument:
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        result = await session.execute(
            update(CommercialDocument)
            .where(
                CommercialDocument.id == document_id,
                CommercialDocument.technical_status == "ready",
                CommercialDocument.lock_version == expected_version,
            )
            .values(lock_version=CommercialDocument.lock_version)
            .returning(CommercialDocument.id)
        )
        if result.scalar_one_or_none() is None:
            raise IssuanceConflict("The commercial document was issued or changed concurrently")
        return await _load_document(session, document_id)

    document = await _load_document(session, document_id, lock=True)
    if document.technical_status != "ready" or document.lock_version != expected_version:
        raise IssuanceConflict("The commercial document was issued or changed concurrently")
    return document


async def _snapshot_payload(
    session: AsyncSession,
    document: CommercialDocument,
    number: str,
    configuration_id: int,
) -> IssuedDocumentSnapshot:
    profile = await session.scalar(
        select(BusinessProfile)
        .where(BusinessProfile.id == document.business_profile_id)
        .options(
            selectinload(BusinessProfile.addresses),
            selectinload(BusinessProfile.tax_identifiers),
            selectinload(BusinessProfile.bank_accounts),
        )
    )
    if profile is None:
        raise ResourceNotFoundError(f"Business profile {document.business_profile_id} was not found")
    buyer = (
        await session.scalar(
            select(Customer)
            .where(Customer.id == document.customer_id)
            .options(
                selectinload(Customer.addresses),
                selectinload(Customer.contacts),
                selectinload(Customer.tax_identifiers),
                selectinload(Customer.accounts).selectinload(CustomerAccount.document_preference),
            )
        )
        if document.customer_id is not None
        else None
    )
    configuration = await session.scalar(
        select(DocumentConfiguration)
        .where(DocumentConfiguration.id == configuration_id)
        .options(
            selectinload(DocumentConfiguration.text_blocks),
            selectinload(DocumentConfiguration.payment_policy),
            selectinload(DocumentConfiguration.einvoice_policy),
        )
    )
    if configuration is None:
        raise ResourceNotFoundError(f"Document configuration {configuration_id} was not found")
    assert document.issue_date is not None

    seller_address = next(
        (item for item in profile.addresses if item.is_default),
        next((item for item in profile.addresses if item.kind == "registered"), None),
    )
    seller_vat = next(
        (item.value for item in profile.tax_identifiers if item.kind == "vat" and item.is_primary),
        next((item.value for item in profile.tax_identifiers if item.kind == "vat"), None),
    )
    seller_tax = next(
        (item.value for item in profile.tax_identifiers if item.kind != "vat" and item.is_primary),
        next((item.value for item in profile.tax_identifiers if item.kind != "vat"), None),
    )
    customer_address = None
    customer_contact = None
    customer_vat = None
    customer_tax = None
    customer_account = None
    preference = None
    if buyer is not None:
        customer_address = next(
            (item for item in buyer.addresses if item.is_default),
            next((item for item in buyer.addresses if item.kind == "billing"), None),
        )
        customer_contact = next(
            (item for item in buyer.contacts if item.include_on_documents and item.is_primary),
            next((item for item in buyer.contacts if item.include_on_documents), None),
        )
        customer_vat = next(
            (item.value for item in buyer.tax_identifiers if item.kind == "vat"),
            None,
        )
        customer_tax = next(
            (item.value for item in buyer.tax_identifiers if item.kind != "vat"),
            None,
        )
        customer_account = next(
            (
                item
                for item in buyer.accounts
                if item.business_profile_id == document.business_profile_id and item.is_active
            ),
            None,
        )
        preference = customer_account.document_preference if customer_account is not None else None

    einvoice_policy = configuration.einvoice_policy
    customer_requirement = preference.einvoice_requirement if preference is not None else "inherit"
    einvoice_required = bool(
        buyer is not None
        and einvoice_policy is not None
        and (
            customer_requirement == "required"
            or (customer_requirement == "inherit" and einvoice_policy.requirement == "rule_required")
        )
    )
    seller_endpoint = einvoice_policy.seller_identifier if einvoice_policy is not None else None
    seller_endpoint_scheme = einvoice_policy.seller_identifier_scheme if einvoice_policy is not None else None
    if seller_endpoint and seller_endpoint_scheme and seller_endpoint.startswith(f"{seller_endpoint_scheme}:"):
        seller_endpoint = seller_endpoint.split(":", 1)[1]
    policy_requirements = dict(einvoice_policy.recipient_requirements or {}) if einvoice_policy is not None else {}
    buyer_endpoint = preference.endpoint_id if preference is not None else None
    buyer_endpoint_scheme = preference.endpoint_scheme if preference is not None else None
    if not buyer_endpoint and customer_contact is not None and customer_contact.email:
        buyer_endpoint = customer_contact.email
        buyer_endpoint_scheme = "EM"
    buyer_reference = None
    if preference is not None:
        buyer_reference = preference.buyer_reference or preference.leitweg_id
    buyer_reference = buyer_reference or (document.content_options or {}).get("buyer_reference")

    bank_account_id = None
    if einvoice_policy is not None and einvoice_policy.bank_account_id is not None:
        bank_account_id = einvoice_policy.bank_account_id
    elif configuration.payment_policy is not None:
        bank_account_id = configuration.payment_policy.bank_account_id
    bank_account = next(
        (item for item in profile.bank_accounts if item.id == bank_account_id),
        next((item for item in profile.bank_accounts if item.is_default), None),
    )
    payment_method = einvoice_policy.default_payment_method if einvoice_policy is not None else None
    payment_means_code = {
        "bank_transfer": "58",
        "credit_transfer": "58",
        "sepa_transfer": "58",
        "direct_debit": "59",
        "card": "48",
        "cash": "10",
    }.get(str(payment_method or "").lower(), "58" if bank_account and bank_account.iban else "30")
    payment_terms = next(
        (item.body for item in configuration.text_blocks if item.purpose == "payment_terms"),
        None,
    )
    if payment_terms:
        payment_terms = payment_terms.replace("{DOCUMENT_NUMBER}", number)
        payment_terms = payment_terms.replace("{DUE_DATE}", document.due_date.isoformat() if document.due_date else "")

    references: list[dict] = []
    if preference is not None and preference.purchase_order_reference:
        references.append({"kind": "order", "identifier": preference.purchase_order_reference})
    for relation in document.incoming_relations:
        relation_number = (relation.relation_data or {}).get("document_number")
        if relation_number:
            references.append(
                {
                    "kind": relation.relation_type,
                    "identifier": str(relation_number),
                }
            )

    standard = "xrechnung"
    syntax = einvoice_policy.syntax if einvoice_policy is not None else "ubl_2_1"
    profile_name = "xrechnung"
    if str(syntax).lower() in {"cii_d22b", "cii-d22b", "zugferd"}:
        standard = "zugferd"
        profile_name = str(einvoice_policy.zugferd_profile or "EN16931").lower()
    return IssuedDocumentSnapshot(
        document_type=document.document_type,
        number=number,
        issue_date=document.issue_date,
        service_date=document.service_date,
        due_date=document.due_date,
        language=document.language,
        currency=document.currency,
        seller={
            "id": profile.id,
            "name": profile.legal_name,
            "country_code": profile.country_code,
            "address": (
                {
                    "line1": seller_address.street,
                    "line2": seller_address.street_2 or seller_address.additional,
                    "postal_code": seller_address.postal_code,
                    "city": seller_address.city,
                    "country_code": seller_address.country_code,
                }
                if seller_address is not None
                else {}
            ),
            "vat_id": seller_vat,
            "tax_id": seller_tax,
            "electronic_address": seller_endpoint,
            "electronic_address_scheme": seller_endpoint_scheme,
            "contact": {
                "name": policy_requirements.get("seller_contact_name"),
                "email": policy_requirements.get("seller_contact_email"),
                "phone": policy_requirements.get("seller_contact_phone"),
            },
            "addresses": [
                {
                    "kind": item.kind,
                    "street": item.street,
                    "postal_code": item.postal_code,
                    "city": item.city,
                    "country_code": item.country_code,
                }
                for item in profile.addresses
            ],
            "tax_identifiers": [
                {"kind": item.kind, "value": item.value, "country_code": item.country_code}
                for item in profile.tax_identifiers
            ],
        },
        buyer={
            "id": buyer.id if buyer is not None else None,
            "name": buyer.display_name if buyer is not None else "",
            "address": (
                {
                    "line1": customer_address.street,
                    "line2": customer_address.street_2 or customer_address.additional,
                    "postal_code": customer_address.postal_code,
                    "city": customer_address.city,
                    "country_code": customer_address.country_code,
                }
                if customer_address is not None
                else {}
            ),
            "contact": (
                {
                    "name": " ".join(
                        part for part in (customer_contact.first_name, customer_contact.last_name) if part
                    ),
                    "email": customer_contact.email,
                    "phone": customer_contact.phone,
                }
                if customer_contact is not None
                else {}
            ),
            "vat_id": customer_vat,
            "tax_id": customer_tax,
            "registration_id": customer_account.number if customer_account is not None else None,
            "electronic_address": buyer_endpoint,
            "electronic_address_scheme": buyer_endpoint_scheme,
            "buyer_reference": buyer_reference,
        },
        lines=tuple(
            SnapshotLine(
                position=line.position,
                description=line.description,
                quantity=line.quantity,
                unit_code=line.unit_code,
                unit_price=line.unit_price,
                net_amount=line.net_amount,
                tax_category_code=line.tax_category_code,
                tax_rate=line.tax_rate,
                product_identifier=line.product_identifier,
                metadata=dict(line.source_data or {}),
            )
            for line in document.lines
        ),
        totals={
            "line_net": document.subtotal_amount,
            "tax": document.tax_amount,
            "payable": document.total_amount,
            "open": document.open_amount,
        },
        payment={
            "due_date": document.due_date,
            "term_days": (
                configuration.payment_policy.payment_term_days if configuration.payment_policy is not None else None
            ),
            "means_code": payment_means_code,
            "terms": payment_terms,
            "iban": bank_account.iban if bank_account is not None else None,
            "bic": bank_account.bic if bank_account is not None else None,
            "account_name": bank_account.account_holder if bank_account is not None else None,
        },
        references=tuple(references),
        text_blocks=tuple(
            {
                "purpose": block.purpose,
                "body": block.body,
                "position": block.position,
            }
            for block in configuration.text_blocks
        ),
        metadata={
            "tax_decision": dict(document.tax_decision or {}),
            "einvoice": {
                "required": einvoice_required,
                "standard": standard,
                "syntax": syntax,
                "profile": profile_name,
                "en16931_version": (einvoice_policy.en16931_version if einvoice_policy is not None else None),
                "cius_name": einvoice_policy.cius_name if einvoice_policy is not None else None,
                "cius_version": (einvoice_policy.cius_version if einvoice_policy is not None else None),
            },
        },
    )


async def issue_document(
    session: AsyncSession,
    document_id: int,
    expected_version: int,
    actor_id: int | None,
    idempotency_key: str,
    correlation_id: str,
) -> CommercialDocument:
    if not idempotency_key.strip():
        raise ValueError("An idempotency key is required")
    if not correlation_id.strip():
        raise ValueError("A correlation ID is required")

    existing = await _existing_reservation(session, idempotency_key)
    if existing is not None and existing.document_id != document_id:
        raise IssuanceConflict("The idempotency key belongs to a different document")
    if existing is not None and existing.status == "consumed":
        return await _reload_issued_document(session, document_id)

    context = await _prepare_issuance(session, document_id, expected_version)
    if existing is not None:
        _assert_reservation_binding(
            existing,
            document_id=document_id,
            intent_sha256=context.intent_sha256,
        )
        await session.rollback()
        await _wait_for_issue_replay(session, existing.id)
        return await _reload_issued_document(session, document_id)

    await session.rollback()
    reservation, created = await _reserve_issue_evidence(
        session,
        document_id=document_id,
        effective_date=context.issue_date,
        idempotency_key=idempotency_key.strip(),
        intent_sha256=context.intent_sha256,
    )
    if not created:
        await _wait_for_issue_replay(session, reservation.id)
        return await _reload_issued_document(session, document_id)

    sessions = _evidence_sessions(session)
    async with sessions() as evidence_session:
        await append_audit(
            evidence_session,
            action="render_start",
            object_type="commercial_document",
            object_id=document_id,
            actor_id=actor_id,
            reason=None,
            before=None,
            after={
                "number_reservation_id": reservation.id,
                "idempotency_key": idempotency_key.strip(),
            },
            correlation_id=correlation_id.strip(),
        )
        await evidence_session.commit()

    try:
        document = await _lock_ready_document(session, document_id, expected_version)
        if _document_intent_sha256(document) != context.intent_sha256:
            raise IssuanceConflict("Document content changed after number reservation")
        snapshot = await _snapshot_payload(
            session,
            document,
            reservation.number,
            context.configuration_id,
        )
        artifact = await generate_required_artifact(session, document, snapshot)
        if artifact is not None:
            if artifact.sha256 != sha256(artifact.content).hexdigest():
                raise EInvoiceValidationFailed("Generated artifact hash does not match its content")
            if artifact.validation_status != "valid":
                raise EInvoiceValidationFailed("Generated electronic invoice is invalid")

        document.number = reservation.number
        document.technical_status = "issued"
        document.lock_version += 1
        evidence = await attach_issued_snapshot(
            session,
            document,
            snapshot,
            configuration_id=context.configuration_id,
            configuration_version=context.configuration_version,
            tax_rule_version=context.tax_rule_version,
            einvoice_rule_versions=context.einvoice_rule_versions,
            actor_id=actor_id,
        )
        stored_einvoice = None
        if artifact is not None:
            stored_einvoice = await store_artifact(
                session,
                document,
                artifact.content,
                artifact.report,
                artifact.rule_versions,
                snapshot_sha256=evidence.sha256,
            )
        await session.flush()
        await render_issued_pdf(
            session,
            document,
            evidence,
            snapshot,
            actor_id=actor_id,
            idempotency_key=idempotency_key.strip(),
            correlation_id=correlation_id.strip(),
            einvoice_artifact=stored_einvoice,
        )
        await append_audit(
            session,
            action="issue",
            object_type="commercial_document",
            object_id=document.id,
            actor_id=actor_id,
            reason="Document approved and issued",
            before={"technical_status": "ready", "lock_version": expected_version},
            after={
                "technical_status": "issued",
                "number": reservation.number,
                "snapshot_sha256": evidence.sha256,
            },
            correlation_id=correlation_id.strip(),
        )
        await session.flush()
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failure_code = getattr(exc, "failure_code", "issuance_failed")
        await _mark_reservation(
            session,
            reservation.id,
            "voided",
            failure_code=str(failure_code),
            failure_detail=str(exc),
        )
        failure_sessions = _evidence_sessions(session)
        async with failure_sessions() as evidence_session:
            await append_audit(
                evidence_session,
                action="render_failure",
                object_type="commercial_document",
                object_id=document_id,
                actor_id=actor_id,
                reason=None,
                before=None,
                after={"code": str(failure_code), "message": str(exc)[:1000]},
                correlation_id=correlation_id.strip(),
            )
            await evidence_session.commit()
        raise

    await _mark_reservation(session, reservation.id, "consumed")
    return await _reload_issued_document(session, document_id)


__all__ = [
    "DocumentFinding",
    "DocumentValidationFailed",
    "EInvoiceValidationFailed",
    "GeneratedArtifact",
    "InvalidDocumentTransition",
    "IssuanceConflict",
    "TECHNICAL_TRANSITIONS",
    "cancel_document",
    "correct_document",
    "create_draft",
    "create_successor",
    "generate_required_artifact",
    "issue_document",
    "mark_ready",
    "transition_document",
    "update_draft",
    "validate_document",
    "validate_draft",
]
