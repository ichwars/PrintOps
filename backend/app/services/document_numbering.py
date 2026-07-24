from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.commercial_document import (
    CommercialDocument,
    DocumentNumberReservation,
)
from backend.app.models.number_sequence import NumberSequence
from backend.app.services.document_catalog import DocumentType
from backend.app.services.number_sequence import reserve_number
from backend.app.services.order_errors import ResourceNotFoundError

DOCUMENT_SEQUENCE_KEYS: dict[DocumentType, str] = {
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


def document_sequence_key(document_type: str) -> str:
    try:
        return DOCUMENT_SEQUENCE_KEYS[DocumentType(document_type)]
    except ValueError as exc:
        raise ValueError(f"Unsupported commercial document type {document_type!r}") from exc


async def reserve_document_number(
    session: AsyncSession,
    document: CommercialDocument,
    effective_date: date,
    *,
    idempotency_key: str | None = None,
    intent_sha256: str | None = None,
) -> DocumentNumberReservation:
    if document.id is None:
        raise ValueError("The document must be persisted before reserving a number")
    sequence_key = document_sequence_key(document.document_type)
    sequence = await session.scalar(
        select(NumberSequence).where(
            NumberSequence.business_profile_id == document.business_profile_id,
            NumberSequence.key == sequence_key,
        )
    )
    if sequence is None:
        raise ResourceNotFoundError(
            f"Number sequence not found for business profile {document.business_profile_id} and key {sequence_key!r}"
        )
    number = document.number
    if number is None:
        number = await reserve_number(
            session,
            business_profile_id=document.business_profile_id,
            key=sequence_key,
            effective_date=effective_date,
        )

    reservation = DocumentNumberReservation(
        document_id=document.id,
        business_profile_id=document.business_profile_id,
        sequence_id=sequence.id,
        number=number,
        idempotency_key=idempotency_key,
        intent_sha256=intent_sha256,
        status="reserved",
    )
    session.add(reservation)
    return reservation
