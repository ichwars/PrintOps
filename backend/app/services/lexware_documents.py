"""Fetch outside transactions; publish complete external snapshots without issuing local documents."""

import json
from datetime import datetime, timezone
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.lexware import LexwareConnection
from backend.app.models.lexware_documents import LexwareDocument, LexwarePaymentSnapshot
from backend.app.services.lexware_client import LexwareClient, LexwareError
from backend.app.services.lexware_document_finance import FINANCIAL_TYPES, iso_date, money, payment_is_complete

DETAIL_ENDPOINTS = {
    "invoice": "invoices",
    "creditnote": "credit-notes",
    "quotation": "quotations",
    "orderconfirmation": "order-confirmations",
    "salesinvoice": "vouchers",
    "salescreditnote": "vouchers",
    "purchaseinvoice": "vouchers",
    "purchasecreditnote": "vouchers",
}


def external_id(value) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError):
        raise LexwareError("Lexware returned an invalid voucher identifier") from None


def file_sources(payload: dict) -> dict[str, str]:
    detail = payload.get("detail", {})
    summary = payload.get("summary", {})
    kind = summary.get("voucherType")
    if kind in {"invoice", "creditnote", "quotation", "orderconfirmation"}:
        if detail.get("voucherStatus", summary.get("voucherStatus")) in {"draft", "unchecked"}:
            return {}
        identifier = external_id(summary.get("id"))
        # Always use sales-file subresources: their wildcard Accept returns the original
        # (XML for XRechnung), while legacy /files/{documentFileId} returns a PDF preview.
        # https://developers.lexware.io/docs/#download-an-invoice-file
        # Versioned internal IDs preserve earlier cached evidence when sales content changes.
        revision = detail.get("version", detail.get("updatedDate", summary.get("updatedDate", "initial")))
        cache_id = str(uuid5(NAMESPACE_URL, f"lexware:{kind}:{identifier}:{revision}"))
        return {cache_id: f"/v1/{DETAIL_ENDPOINTS[kind]}/{identifier}/file"}
    files = detail.get("files", [])
    if isinstance(files, dict):
        files = [files.get("documentFileId")]
    if files is None:
        files = []
    if not isinstance(files, list):
        raise LexwareError("Lexware returned invalid original-file references")
    result = []
    for value in files:
        if isinstance(value, dict):
            value = value.get("id")
        if value:
            result.append(external_id(value))
    return {identifier: f"/v1/files/{identifier}" for identifier in dict.fromkeys(result)}


def file_ids(payload: dict) -> list[str]:
    return list(file_sources(payload))


async def fetch_vouchers(client: LexwareClient) -> list[dict]:
    summaries = await client.list_pages("/v1/voucherlist", {"voucherType": "any", "voucherStatus": "any"})
    rows = []
    for summary in summaries:
        identifier = external_id(summary.get("id"))
        kind = summary.get("voucherType")
        endpoint = DETAIL_ENDPOINTS.get(kind)
        detail = await client.get_json(f"/v1/{endpoint}/{identifier}") if endpoint else {}
        if not isinstance(detail, dict) or (endpoint and external_id(detail.get("id")) != identifier):
            raise LexwareError("Lexware returned inconsistent voucher details")
        payload = {"summary": summary, "detail": detail}
        file_ids(payload)  # Validate references before publishing any of the run.
        payment = None
        state = "not_applicable" if kind not in FINANCIAL_TYPES else "unknown"
        status = detail.get("voucherStatus", summary.get("voucherStatus", "unknown"))
        if kind in FINANCIAL_TYPES and status not in {"draft", "unchecked", "voided"}:
            try:
                payment = await client.get_json(f"/v1/payments/{identifier}")
            except LexwareError as exc:
                # A missing scope or unsupported payment resource must never imply paid.
                if exc.status_code not in {403, 404, 406}:
                    raise
            currency = summary.get("currency") or detail.get("totalPrice", {}).get("currency", "EUR")
            state = "known" if payment_is_complete(payment, currency) else "unknown"
        elif kind in FINANCIAL_TYPES:
            state = "not_applicable"
        rows.append({**payload, "payment": payment if isinstance(payment, dict) else None, "payment_state": state})
    return rows


async def replace_vouchers(db: AsyncSession, connection_id: int, rows: list[dict]) -> None:
    """Upsert a complete run inside the caller's generation-checked transaction.

    Retain disappeared vouchers, originals and local links as historical evidence.
    Never commit here: contacts/articles/vouchers publish as one unit in the owner.
    """
    connection = await db.get(LexwareConnection, connection_id)
    if connection is None:
        raise LexwareError("Lexware connection was not found")
    # Identity validation precedes writes, including rows not reached if an earlier upsert failed.
    for row in rows:
        for resource in (row["summary"], row["detail"], row.get("payment")):
            organization = resource.get("organizationId") if isinstance(resource, dict) else None
            if organization is not None and organization != connection.organization_id:
                raise LexwareError("Lexware returned a voucher from a different organization")
    existing = {
        d.external_id: d
        for d in (await db.scalars(select(LexwareDocument).where(LexwareDocument.connection_id == connection_id))).all()
    }
    seen = set()
    for row in rows:
        summary, detail = row["summary"], row["detail"]
        identifier = external_id(summary.get("id"))
        if identifier in seen:
            raise LexwareError("Lexware returned duplicate vouchers")
        seen.add(identifier)
        digest = sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        document = existing.get(identifier)
        if document is None:
            document = LexwareDocument(connection_id=connection_id, external_id=identifier, version=1)
            db.add(document)
        elif document.version_hash != digest or not document.in_latest_sync:
            document.version += 1
        document.voucher_type = str(summary.get("voucherType", "unknown"))[:64]
        document.voucher_status = str(detail.get("voucherStatus", summary.get("voucherStatus", "unknown")))[:64]
        document.voucher_number = str(summary.get("voucherNumber") or detail.get("voucherNumber") or "")[:255] or None
        document.voucher_date = iso_date(summary.get("voucherDate") or detail.get("voucherDate"))
        document.due_date = iso_date(summary.get("dueDate") or detail.get("dueDate"))
        document.contact_name = (
            str(summary.get("contactName") or detail.get("address", {}).get("name") or "")[:500] or None
        )
        document.currency = str(summary.get("currency") or detail.get("totalPrice", {}).get("currency") or "EUR")[:3]
        gross = detail.get("totalPrice", {}).get("totalGrossAmount", detail.get("totalGrossAmount"))
        document.total_amount = money(gross if gross is not None else summary.get("totalAmount"))
        document.supported = document.voucher_type in DETAIL_ENDPOINTS
        document.archived = bool(summary.get("archived", False))
        document.in_latest_sync = True
        document.payload = {"summary": summary, "detail": detail}
        document.version_hash = digest
        document.updated_at = datetime.now(timezone.utc)
        await db.flush()
        payment = await db.scalar(
            select(LexwarePaymentSnapshot).where(LexwarePaymentSnapshot.document_id == document.id)
        )
        if payment is None:
            payment = LexwarePaymentSnapshot(document_id=document.id)
            db.add(payment)
        payment.state = row["payment_state"]
        payment.payload = row.get("payment")
        document.payment = payment
    for identifier, document in existing.items():
        if identifier not in seen and document.in_latest_sync:
            document.in_latest_sync = False
            document.version += 1
    await db.flush()
