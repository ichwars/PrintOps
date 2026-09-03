"""Read external evidence and attach a manual local reference; never write upstream."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled, caller_is_api_key
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.commercial_document import CommercialDocument
from backend.app.models.lexware import LexwareConnection
from backend.app.models.lexware_documents import LexwareDocument, LexwareOriginal
from backend.app.models.user import User
from backend.app.schemas.lexware_documents import (
    LexwareCurrencyTotals,
    LexwareDocumentList,
    LexwareDocumentRead,
    LexwareFileRead,
    LexwareFinanceRead,
    LexwareLinkCommand,
)
from backend.app.services.lexware_client import LexwareError
from backend.app.services.lexware_connections import lock_connection
from backend.app.services.lexware_document_finance import FINAL_STATUSES, FINANCIAL_TYPES, project_finance
from backend.app.services.lexware_document_originals import get_original
from backend.app.services.lexware_documents import file_ids

router = APIRouter(prefix="/lexware", tags=["lexware-documents"])
READ = Permission.COMMERCIAL_DOCUMENTS_READ
FINANCE = Permission.PAYMENTS_READ


def _filters(connection_id: int | None, business_profile_id: int | None):
    filters = []
    if connection_id is not None:
        filters.append(LexwareDocument.connection_id == connection_id)
    if business_profile_id is not None:
        filters.append(LexwareConnection.business_profile_id == business_profile_id)
    return filters


async def _load(db: AsyncSession, document_id: int):
    row = (
        await db.execute(
            select(LexwareDocument, LexwareConnection)
            .join(LexwareConnection, LexwareDocument.connection_id == LexwareConnection.id)
            .where(LexwareDocument.id == document_id)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Lexware document was not found")
    return row


async def _read(db: AsyncSession, document: LexwareDocument, connection: LexwareConnection, financial: bool):
    result = LexwareDocumentRead(
        source="lexware",
        id=document.id,
        connection_id=connection.id,
        business_profile_id=connection.business_profile_id,
        company_name=connection.company_name,
        external_id=document.external_id,
        voucher_type=document.voucher_type,
        voucher_status=(
            "final" if not financial and document.voucher_status in FINAL_STATUSES else document.voucher_status
        ),
        voucher_number=document.voucher_number,
        voucher_date=document.voucher_date,
        contact_name=document.contact_name,
        supported=document.supported,
        archived=document.archived,
        in_latest_sync=document.in_latest_sync,
        connection_enabled=bool(connection.enabled and connection.encrypted_api_key),
        sync_status=connection.sync_status,
        last_success_at=connection.last_success_at,
        updated_at=document.updated_at,
        version=document.version,
        local_document_id=document.local_document_id,
    )
    if financial:
        cached = {
            row.file_id: row
            for row in (
                await db.scalars(select(LexwareOriginal).where(LexwareOriginal.document_id == document.id))
            ).all()
        }
        result.due_date = document.due_date
        result.finance = project_finance(document)
        result.files = [
            LexwareFileRead(
                file_id=identifier,
                cached=identifier in cached,
                **(
                    {
                        field: getattr(cached[identifier], field)
                        for field in ("filename", "media_type", "size_bytes", "sha256", "cached_at")
                    }
                    if identifier in cached
                    else {}
                ),
            )
            for identifier in dict.fromkeys([*file_ids(document.payload), *cached])
        ]
    return result


@router.get("/documents", response_model=LexwareDocumentList, response_model_exclude_unset=True)
async def list_documents(
    connection_id: int | None = None,
    business_profile_id: int | None = None,
    search: str = Query("", max_length=200),
    voucher_type: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(READ),
    api_key: bool = Depends(caller_is_api_key),
):
    filters = _filters(connection_id, business_profile_id)
    if search:
        filters.append(
            or_(
                LexwareDocument.voucher_number.contains(search, autoescape=True),
                LexwareDocument.contact_name.contains(search, autoescape=True),
            )
        )
    if voucher_type:
        filters.append(LexwareDocument.voucher_type == voucher_type)
    statement = select(LexwareDocument, LexwareConnection).join(LexwareConnection).where(*filters)
    total = await db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = (
        await db.execute(
            statement.order_by(LexwareDocument.voucher_date.desc(), LexwareDocument.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    financial = not api_key and (actor is None or actor.has_all_permissions(FINANCE.value))
    return LexwareDocumentList(items=[await _read(db, d, c, financial) for d, c in rows], total=total)


@router.get("/finance", response_model=LexwareFinanceRead)
async def finance(
    connection_id: int | None = None,
    business_profile_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(READ, FINANCE),
):
    rows = (
        await db.execute(
            select(LexwareDocument, LexwareConnection)
            .join(LexwareConnection)
            .where(*_filters(connection_id, business_profile_id))
        )
    ).all()
    currencies = {}
    included = linked = unknown = excluded = unsupported = 0
    stale = set()
    for document, connection in rows:
        projected = project_finance(document)
        if not connection.enabled or not connection.encrypted_api_key or connection.sync_status in {"error", "failed"}:
            stale.add(connection.id)
        linked += int(document.local_document_id is not None)
        unsupported += int(not document.supported)
        unknown += int(projected.payment_state == "unknown" and document.voucher_type in FINANCIAL_TYPES)
        if not projected.included_in_totals:
            excluded += 1
            continue
        included += 1
        total = currencies.setdefault(document.currency, LexwareCurrencyTotals(currency=document.currency))
        signed_open = projected.open_amount * (Decimal("-1") if projected.credit else Decimal("1"))
        field = "receivables" if projected.direction == "receivable" else "payables"
        setattr(total, field, getattr(total, field) + signed_open)
        if projected.overdue:
            setattr(total, f"overdue_{field}", getattr(total, f"overdue_{field}") + signed_open)
        total.document_count += 1
    return LexwareFinanceRead(
        as_of=date.today(),
        totals=[currencies[key] for key in sorted(currencies)],
        included_count=included,
        linked_count=linked,
        unknown_count=unknown,
        excluded_count=excluded,
        unsupported_count=unsupported,
        stale_connection_count=len(stale),
    )


@router.get("/documents/{document_id}", response_model=LexwareDocumentRead, response_model_exclude_unset=True)
async def document_detail(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(READ),
    api_key: bool = Depends(caller_is_api_key),
):
    document, connection = await _load(db, document_id)
    return await _read(
        db, document, connection, not api_key and (actor is None or actor.has_all_permissions(FINANCE.value))
    )


_LOCAL_TYPES = {
    "invoice": {"invoice", "advance_invoice", "progress_invoice", "final_invoice"},
    "salesinvoice": {"invoice", "advance_invoice", "progress_invoice", "final_invoice"},
    "creditnote": {"invoice_correction", "commercial_credit_note", "cancellation_invoice"},
    "salescreditnote": {"invoice_correction", "commercial_credit_note", "cancellation_invoice"},
    "purchaseinvoice": {"self_billing"},
    "quotation": {"quotation"},
    "orderconfirmation": {"order_confirmation"},
}


@router.put("/documents/{document_id}/link", response_model=LexwareDocumentRead, response_model_exclude_unset=True)
async def link_document(
    document_id: int,
    command: LexwareLinkCommand,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(READ, FINANCE, Permission.COMMERCIAL_DOCUMENTS_DRAFT),
):
    # Serialize with the scheduler and downloads in the same connection-then-document lock order.
    connection_id = await db.scalar(select(LexwareDocument.connection_id).where(LexwareDocument.id == document_id))
    if connection_id is None:
        raise HTTPException(404, "Lexware document was not found")
    await lock_connection(db, connection_id)
    # Take the write lock using the optimistic version before validating or mutating links.
    result = await db.execute(
        update(LexwareDocument)
        .where(
            LexwareDocument.id == document_id,
            LexwareDocument.version == command.expected_version,
        )
        .values(version=LexwareDocument.version + 1)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(409, "Lexware document changed; reload before linking")
    document, connection = await _load(db, document_id)
    if command.local_document_id is not None:
        local = await db.get(CommercialDocument, command.local_document_id)
        if local is None or local.business_profile_id != connection.business_profile_id:
            raise HTTPException(422, "Choose a local document from the same business profile")
        if local.document_type not in _LOCAL_TYPES.get(document.voucher_type, set()):
            raise HTTPException(422, "The local document type is incompatible")
        if document.voucher_type in FINANCIAL_TYPES and (
            local.technical_status != "issued"
            or local.currency != document.currency
            or document.total_amount is None
            or abs(local.total_amount) != abs(document.total_amount)
        ):
            raise HTTPException(422, "Link requires an issued local document with the same currency and gross amount")
    document.local_document_id = command.local_document_id
    document.linked_by_id = actor.id if actor else None
    document.linked_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "This local document is already linked to a Lexware voucher") from None
    await db.refresh(document)
    return await _read(db, document, connection, True)


@router.get("/documents/{document_id}/files/{file_id}")
async def original_file(
    document_id: int,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User | None = RequirePermissionIfAuthEnabled(READ, FINANCE),
):
    document, connection = await _load(db, document_id)
    try:
        original = await get_original(db, document, connection, str(file_id))
    except LexwareError:
        raise HTTPException(502, "Lexware original is unavailable; no cached evidence was changed") from None
    return Response(
        original.content,
        media_type=original.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{original.filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "sandbox",
            "ETag": f'"{original.sha256}"',
        },
    )
