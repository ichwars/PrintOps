from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.commercial_document import (
    CommercialDocument,
    CommercialDocumentLine,
    DocumentRelation,
)
from backend.app.schemas.commercial_document import (
    CommercialDocumentDraft,
    CommercialDocumentLineDraft,
)
from backend.app.services.document_audit import append_audit
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, DocumentType
from backend.app.services.order_errors import ResourceInUseError, ResourceNotFoundError, VersionConflictError


class InvalidDocumentTransition(ResourceInUseError):
    pass


class DocumentValidationFailed(ResourceInUseError):
    def __init__(self, findings: tuple[DocumentFinding, ...]):
        super().__init__("The commercial document is not ready")
        self.findings = findings


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
        prior_by_group[group] = prior_by_group.get(group, Decimal("0")) + Decimal(
            str(item.get("gross") or "0")
        )
    for item in deductions:
        group = _tax_group(item)
        deduction_by_group[group] = deduction_by_group.get(group, Decimal("0")) + Decimal(
            str(item.get("gross") or "0")
        )

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
    successor.incoming_relations = [
        DocumentRelation(source_document_id=source.id, relation_type=relation_type)
    ]
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


__all__ = [
    "DocumentFinding",
    "DocumentValidationFailed",
    "InvalidDocumentTransition",
    "TECHNICAL_TRANSITIONS",
    "cancel_document",
    "correct_document",
    "create_draft",
    "create_successor",
    "mark_ready",
    "transition_document",
    "update_draft",
    "validate_document",
    "validate_draft",
]
