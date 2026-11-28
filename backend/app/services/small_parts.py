from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.small_part import SmallPart, SmallPartCategory, SmallPartLedgerEntry
from backend.app.schemas.small_part import SmallPartUpdate
from backend.app.services.warehouse_number_sequence import reserve_number


class SmallPartNotFound(LookupError):
    def __init__(self, small_part_id: int):
        self.small_part_id = small_part_id
        super().__init__(f"Material {small_part_id} was not found")


class InsufficientSmallPartStock(ValueError):
    def __init__(self, small_part_id: int, available: Decimal):
        self.small_part_id = small_part_id
        self.available = available
        super().__init__(f"Material {small_part_id} has insufficient stock ({available} available)")


class SmallPartInactive(ValueError):
    pass


class SmallPartUnitChangeNotAllowed(ValueError):
    pass


class SmallPartIdempotencyConflict(ValueError):
    pass


@dataclass(frozen=True)
class SmallPartBalance:
    physical: Decimal
    reserved: Decimal
    available: Decimal


@dataclass(frozen=True)
class StockUsage:
    last_used_at: datetime | None = None
    consumed: Decimal = Decimal("0")


async def usage_for_parts(session: AsyncSession, ids: list[int]) -> dict[int, StockUsage]:
    if not ids:
        return {}
    entries = SmallPartLedgerEntry
    rows = await session.execute(
        select(entries.small_part_id, func.max(entries.created_at), func.sum(entries.physical_delta))
        .where(entries.small_part_id.in_(ids), entries.entry_kind == "issue")
        .group_by(entries.small_part_id)
    )
    return {identifier: StockUsage(last_used, -quantity) for identifier, last_used, quantity in rows}


@dataclass(frozen=True)
class SmallPartSearchResult:
    part: SmallPart
    available: Decimal


async def get_balance(session: AsyncSession, small_part_id: int) -> SmallPartBalance:
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(SmallPartLedgerEntry.physical_delta), 0),
                func.coalesce(func.sum(SmallPartLedgerEntry.reserved_delta), 0),
            ).where(SmallPartLedgerEntry.small_part_id == small_part_id)
        )
    ).one()
    physical = Decimal(row[0])
    reserved = Decimal(row[1])
    return SmallPartBalance(physical=physical, reserved=reserved, available=physical - reserved)


async def append_ledger_entry(
    session: AsyncSession,
    *,
    small_part_id: int,
    entry_kind: str,
    physical_delta: Decimal,
    reserved_delta: Decimal,
    reason: str,
    idempotency_key: str,
    reference_type: str | None = None,
    reference_id: int | None = None,
    actor_id: int | None = None,
    require_active: bool = False,
) -> SmallPartLedgerEntry:
    # Lock before checking for a replay or reading the balance. A no-op write
    # also serializes concurrent SQLite stock writes without changing material metadata.
    await session.execute(
        update(SmallPart)
        .where(SmallPart.id == small_part_id)
        .values(id=SmallPart.id, updated_at=SmallPart.updated_at)
        .execution_options(synchronize_session=False)
    )
    existing = await session.scalar(
        select(SmallPartLedgerEntry).where(SmallPartLedgerEntry.idempotency_key == idempotency_key)
    )
    if existing is not None:
        command_matches = (
            existing.small_part_id == small_part_id
            and existing.entry_kind == entry_kind
            and Decimal(existing.physical_delta) == Decimal(physical_delta)
            and Decimal(existing.reserved_delta) == Decimal(reserved_delta)
            and existing.reason == reason.strip()
            and existing.reference_type == reference_type
            and existing.reference_id == reference_id
            and existing.actor_id == actor_id
        )
        if not command_matches:
            raise SmallPartIdempotencyConflict("Idempotency key belongs to a different stock command")
        return existing

    part = await session.scalar(
        select(SmallPart).where(SmallPart.id == small_part_id).execution_options(populate_existing=True)
    )
    if part is None:
        raise SmallPartNotFound(small_part_id)
    if require_active and not part.is_active:
        raise SmallPartInactive(f"Material {small_part_id} is inactive")

    current = await get_balance(session, small_part_id)
    next_physical = current.physical + Decimal(physical_delta)
    next_reserved = current.reserved + Decimal(reserved_delta)
    if next_physical < 0 or next_reserved < 0 or next_reserved > next_physical:
        raise InsufficientSmallPartStock(small_part_id, next_physical - next_reserved)

    receipt_number = await reserve_number(session, key="goods_receipt") if entry_kind == "receipt" else None
    entry = SmallPartLedgerEntry(
        small_part_id=small_part_id,
        receipt_number=receipt_number,
        entry_kind=entry_kind,
        physical_delta=physical_delta,
        reserved_delta=reserved_delta,
        reason=reason.strip(),
        reference_type=reference_type,
        reference_id=reference_id,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    session.add(entry)
    await session.flush()
    return entry


async def search_small_parts(
    session: AsyncSession,
    *,
    query: str = "",
    active_only: bool = True,
    limit: int = 30,
) -> list[SmallPartSearchResult]:
    statement = (
        select(SmallPart)
        .outerjoin(SmallPartCategory, SmallPart.category_id == SmallPartCategory.id)
        .options(selectinload(SmallPart.category), selectinload(SmallPart.unit), selectinload(SmallPart.location))
    )
    normalized = query.strip().lower()
    if normalized:
        pattern = f"%{normalized}%"
        statement = statement.where(
            or_(
                func.lower(SmallPart.sku).like(pattern),
                func.lower(SmallPart.name).like(pattern),
                func.lower(func.coalesce(SmallPart.description, "")).like(pattern),
                func.lower(func.coalesce(SmallPart.search_terms, "")).like(pattern),
                func.lower(func.coalesce(SmallPartCategory.name, "")).like(pattern),
            )
        )
    if active_only:
        statement = statement.where(SmallPart.is_active.is_(True))
    statement = statement.order_by(SmallPart.is_active.desc(), func.lower(SmallPart.name)).limit(limit)
    parts = list((await session.scalars(statement)).unique())
    return [
        SmallPartSearchResult(part=part, available=(await get_balance(session, part.id)).available) for part in parts
    ]


async def update_small_part(
    session: AsyncSession,
    part: SmallPart,
    data: SmallPartUpdate,
) -> SmallPart:
    changes = data.model_dump(exclude_unset=True)
    if changes.get("sku"):
        from backend.app.services.warehouse_number_sequence import assert_material_number_available

        try:
            await assert_material_number_available(session, changes["sku"], exclude_small_part_id=part.id)
        except ValueError as exc:
            raise SmallPartUnitChangeNotAllowed(str(exc)) from exc
    requested_unit = changes.get("unit_code")
    if requested_unit is not None and requested_unit != part.unit_code:
        ledger_count = await session.scalar(
            select(func.count(SmallPartLedgerEntry.id)).where(SmallPartLedgerEntry.small_part_id == part.id)
        )
        if ledger_count:
            raise SmallPartUnitChangeNotAllowed("unit cannot change after the first stock entry")
    for field, value in changes.items():
        setattr(part, field, value)
    await session.flush()
    return part
