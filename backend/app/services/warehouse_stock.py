"""Transactional warehouse commands. No commit and no upstream network access."""

import hashlib
import json
from decimal import Decimal

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.commerce import CustomerOrder
from backend.app.models.location import Location
from backend.app.models.small_part import SmallPartUnit
from backend.app.models.warehouse_article import WarehouseArticleLedgerEntry as Entry
from backend.app.schemas.warehouse_article import WarehouseMovementCreate, WarehouseReservationRead
from backend.app.services.warehouse_articles import (
    MAX_QUANTITY,
    ZERO,
    WarehouseError,
    check_precision,
    load_article,
    location_balances,
)


async def reservation_remaining(session: AsyncSession, reservation: Entry) -> Decimal:
    values = await session.scalars(
        select(Entry.reserved_delta).where(or_(Entry.id == reservation.id, Entry.reservation_id == reservation.id))
    )
    return sum(values, ZERO)


async def open_reservations(session: AsyncSession, article_id: int) -> list[WarehouseReservationRead]:
    entries = await session.scalars(
        select(Entry).where(Entry.article_id == article_id, Entry.entry_kind == "reservation").order_by(Entry.id)
    )
    result = []
    for entry in entries:
        remaining = await reservation_remaining(session, entry)
        if remaining > 0:
            result.append(
                WarehouseReservationRead(
                    id=entry.id, location_id=entry.location_id, order_id=entry.order_id, remaining=remaining
                )
            )
    return result


async def _reservation(session: AsyncSession, identifier: int, article_id: int) -> Entry:
    reservation = await session.get(Entry, identifier)
    if reservation is None or reservation.article_id != article_id or reservation.entry_kind != "reservation":
        raise WarehouseError("invalid_reservation", "Reservierung dieses Artikels nicht gefunden", 422)
    return reservation


async def _command_entry(session: AsyncSession, article_id: int, data: WarehouseMovementCreate) -> dict:
    payload = data.model_dump(exclude={"idempotency_key", "reverses_id"})
    payload.update(physical_delta=ZERO, reserved_delta=ZERO, reverses_id=None)
    if data.entry_kind == "counter":
        original = await session.get(Entry, data.reverses_id)
        if original is None or original.article_id != article_id or original.entry_kind == "counter":
            raise WarehouseError(
                "invalid_reversal", "Ursprüngliche Buchung nicht gefunden oder bereits Gegenbuchung", 422
            )
        if await session.scalar(select(Entry.id).where(Entry.reverses_id == original.id)):
            raise WarehouseError("already_reversed", "Buchung wurde bereits gegengebucht")
        payload.update(
            location_id=original.location_id,
            target_location_id=original.target_location_id,
            quantity=-original.quantity,
            physical_delta=-original.physical_delta,
            reserved_delta=-original.reserved_delta,
            order_id=original.order_id,
            reservation_id=original.id if original.entry_kind == "reservation" else original.reservation_id,
            reverses_id=original.id,
        )
    elif data.entry_kind in {"opening", "receipt", "correction"}:
        payload["physical_delta"] = data.quantity
    elif data.entry_kind in {"issue", "transfer"}:
        payload["physical_delta"] = -data.quantity
    elif data.entry_kind == "reservation":
        payload["reserved_delta"] = data.quantity
    elif data.entry_kind in {"release", "reserved_issue"}:
        reservation = await _reservation(session, data.reservation_id, article_id)
        if reservation.location_id != data.location_id or (
            data.order_id is not None and reservation.order_id != data.order_id
        ):
            raise WarehouseError("invalid_reservation", "Lagerort oder Auftrag passt nicht zur Reservierung", 422)
        payload["order_id"] = reservation.order_id
        payload["reserved_delta"] = -data.quantity
        if data.entry_kind == "reserved_issue":
            payload["physical_delta"] = -data.quantity
    return payload


async def post_movement(
    session: AsyncSession, article_id: int, data: WarehouseMovementCreate, *, actor_id: int | None = None
) -> Entry:
    article = await load_article(session, article_id, lock=True)
    command = data.model_dump(mode="json", exclude={"idempotency_key"})
    if data.quantity is not None:
        command["quantity"] = format(data.quantity.normalize(), "f")
    command["actor_id"] = actor_id
    digest = hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()
    existing = await session.scalar(
        select(Entry).where(Entry.article_id == article_id, Entry.idempotency_key == data.idempotency_key)
    )
    if existing:
        if existing.command_hash != digest:
            raise WarehouseError("idempotency_conflict", "Buchungsschlüssel gehört zu einem anderen Auftrag")
        return existing
    if not article.is_active:
        raise WarehouseError("article_archived", "Archivierte Artikel können nicht gebucht werden")
    if article.stock_source != "own" or article.kind == "service":
        raise WarehouseError(
            "stock_source_not_own",
            "Buchungen sind nur für eigene Warenbestände möglich; Material bitte in der Materialverwaltung buchen",
        )
    unit = await session.get(SmallPartUnit, article.unit_code)
    if unit is None or not unit.is_active:
        raise WarehouseError("invalid_unit", "Lokale Einheit ist nicht aktiv", 422)
    if data.quantity is not None:
        check_precision(data.quantity, unit)
    payload = await _command_entry(session, article_id, data)
    for location_id in sorted({payload["location_id"], payload["target_location_id"]} - {None}):
        await session.execute(
            update(Location).where(Location.id == location_id).values(id=Location.id, updated_at=Location.updated_at)
        )
        if await session.get(Location, location_id) is None:
            raise WarehouseError("invalid_location", "Lagerort nicht gefunden", 422)
    if payload["order_id"] is not None and await session.get(CustomerOrder, payload["order_id"]) is None:
        raise WarehouseError("invalid_order", "Auftrag nicht gefunden", 422)
    if data.entry_kind == "opening" and await session.scalar(
        select(Entry.id)
        .where(
            Entry.article_id == article_id,
            or_(Entry.location_id == data.location_id, Entry.target_location_id == data.location_id),
        )
        .limit(1)
    ):
        raise WarehouseError("opening_exists", "Anfangsbestand ist nur vor der ersten Buchung am Lagerort möglich")
    if payload["reservation_id"] is not None:
        reservation = await _reservation(session, payload["reservation_id"], article_id)
        remaining = await reservation_remaining(session, reservation) + payload["reserved_delta"]
        if remaining < 0 or remaining > reservation.quantity:
            raise WarehouseError("reservation_exceeded", "Buchung überschreitet die offene Reservierung")
    balances = {row.location_id: (row.physical, row.reserved) for row in await location_balances(session, article)}
    deltas = [(payload["location_id"], payload["physical_delta"], payload["reserved_delta"])]
    if payload["target_location_id"] is not None:
        deltas.append((payload["target_location_id"], -payload["physical_delta"], ZERO))
    for location_id, physical_delta, reserved_delta in deltas:
        physical, reserved = balances.get(location_id, (ZERO, ZERO))
        physical += physical_delta
        reserved += reserved_delta
        if physical < 0 or reserved < 0 or reserved > physical:
            raise WarehouseError(
                "insufficient_stock", "Buchung würde physische oder verfügbare Bestände unterschreiten"
            )
        if physical > MAX_QUANTITY or reserved > MAX_QUANTITY:
            raise WarehouseError("quantity_limit", "Bestand überschreitet den zulässigen Mengenbereich", 422)
    entry = Entry(
        **payload,
        article_id=article_id,
        unit_code=article.unit_code,
        actor_id=actor_id,
        idempotency_key=data.idempotency_key,
        command_hash=digest,
    )
    session.add(entry)
    article.version += 1
    await session.flush()
    return entry
