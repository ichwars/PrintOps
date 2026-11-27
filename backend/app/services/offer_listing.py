"""Pagination for the offer register."""

import re
from decimal import Decimal, InvalidOperation
from unicodedata import combining, normalize

from sqlalchemy import String, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.text_normalization import normalize_case_insensitive_key
from backend.app.models.commerce import CustomerOrder, Offer
from backend.app.models.commercial_document import CommercialDocument, DocumentSnapshot
from backend.app.models.customer import Customer
from backend.app.schemas.commerce import OfferListItemRead, OfferPageQuery, OfferPageRead
from backend.app.services.document_recipients import issued_recipient_name

_CALCULATION_ID = Offer.snapshot["calculation"]["id"].as_string().cast(String)
_CALCULATION_TITLE = Offer.snapshot["calculation"]["title"].as_string()
_QUOTATION = CommercialDocument.document_type == "quotation"
_RECIPIENT_COLUMNS = (DocumentSnapshot.canonical_json, Customer.display_name)
_STATUS_ORDER = ("accepted", "draft", "rejected", "sent")
_NEWEST_FIRST = (Offer.updated_at.desc(), Offer.id.desc())


def _with_recipients(statement):
    return (
        statement.outerjoin(CommercialDocument, CommercialDocument.source_offer_id == Offer.id)
        .outerjoin(DocumentSnapshot, and_(_QUOTATION, DocumentSnapshot.document_id == CommercialDocument.id))
        .outerjoin(Customer, Customer.id == case((_QUOTATION, CommercialDocument.customer_id), else_=Offer.customer_id))
    )


def _recipient(row) -> str | None:
    return issued_recipient_name(row.canonical_json) or row.display_name


def _natural_key(value: str | None):
    if not value:
        return None
    text = normalize("NFD", normalize_case_insensitive_key(value))
    base = "".join(character for character in text if not combining(character))
    return tuple(int(part) if index % 2 else part for index, part in enumerate(re.split(r"(\d+)", base)))


def _number(value, default=None):
    if value is None:
        return default
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


async def _selected_ids(session: AsyncSession, query: OfferPageQuery, conditions: list, needle: str):
    include_recipient = bool(needle) or query.sort_by == "customer"
    statement = (
        select(
            Offer.id,
            Offer.number,
            Offer.customer_id,
            Offer.status,
            Offer.updated_at,
            _CALCULATION_ID.label("calculation_id"),
            _CALCULATION_TITLE.label("calculation_title"),
            Offer.snapshot["revision"]["revision_number"].as_string().label("revision_number"),
            Offer.snapshot["revision"]["selling_price"].as_string().label("selling_price"),
        )
        .where(*conditions)
        .order_by(*_NEWEST_FIRST)
    )
    if include_recipient:
        statement = _with_recipients(statement.add_columns(*_RECIPIENT_COLUMNS))

    statuses = list(dict.fromkeys([*query.status_order, *_STATUS_ORDER]))
    matches = []
    missing = []
    for row in await session.execute(statement):
        recipient = _recipient(row) if include_recipient else None
        title = row.calculation_title
        if title is None:
            title = f"K-{row.calculation_id}" if row.calculation_id is not None else "—"
        if needle and not any(
            needle in normalize_case_insensitive_key(str(value))
            for value in (row.number, title, recipient, f"#{row.customer_id}" if row.customer_id is not None else None)
            if value is not None
        ):
            continue
        if query.sort_by == "number":
            sort_key = _natural_key(row.number)
        elif query.sort_by == "calculation":
            sort_key = _natural_key(str(title))
        elif query.sort_by == "customer":
            sort_key = _natural_key(recipient)
        elif query.sort_by == "revision":
            sort_key = _number(row.revision_number)
        elif query.sort_by == "price":
            sort_key = _number(row.selling_price, Decimal(0))
        elif query.sort_by == "status":
            sort_key = statuses.index(row.status)
        else:
            sort_key = row.updated_at
        if sort_key is None:
            missing.append(row.id)
        else:
            matches.append((sort_key, row.id))
    matches.sort(key=lambda match: match[0], reverse=query.sort_dir == "desc")
    ids = [row_id for _, row_id in matches] + missing
    return ids[query.offset : query.offset + query.limit], len(ids)


async def list_offer_page(session: AsyncSession, query: OfferPageQuery) -> OfferPageRead:
    conditions = [
        column == value
        for column, value in (
            (Offer.status, query.status),
            (Offer.customer_id, query.customer_id),
            (Offer.business_profile_id, query.business_profile_id),
            (func.ltrim(_CALCULATION_ID, "0"), str(query.calculation_id) if query.calculation_id else None),
        )
        if value is not None
    ]
    needle = normalize_case_insensitive_key(query.q.strip())
    statement = _with_recipients(
        select(
            *Offer.__table__.c,
            CustomerOrder.id.label("order_id"),
            CommercialDocument.id.label("quotation_document_id"),
            *_RECIPIENT_COLUMNS,
        )
    ).outerjoin(CustomerOrder, CustomerOrder.offer_id == Offer.id)
    if not needle and query.sort_by == "updated":
        total = await session.scalar(select(func.count()).select_from(Offer).where(*conditions))
        order_by = _NEWEST_FIRST if query.sort_dir == "desc" else (Offer.updated_at.asc(), Offer.id.desc())
        rows = await session.execute(
            statement.where(*conditions).order_by(*order_by).offset(query.offset).limit(query.limit)
        )
        items = [_list_item(row) for row in rows]
    else:
        ids, total = await _selected_ids(session, query, conditions, needle)
        rows = await session.execute(statement.where(Offer.id.in_(ids))) if ids else []
        by_id = {row.id: _list_item(row) for row in rows}
        items = [by_id[offer_id] for offer_id in ids if offer_id in by_id]
    return OfferPageRead(items=items, total=total or 0, offset=query.offset, limit=query.limit)


def _list_item(row) -> OfferListItemRead:
    values = dict(row._mapping)
    values["customer_display_name"] = _recipient(row)
    del values["canonical_json"], values["display_name"]
    return OfferListItemRead.model_validate(values)
