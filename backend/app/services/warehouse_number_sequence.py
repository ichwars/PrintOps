from __future__ import annotations

from datetime import date

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.warehouse_number_sequence import WarehouseNumberSequence
from backend.app.schemas.warehouse_number_sequence import (
    WarehouseNumberSequenceCreate,
    WarehouseNumberSequenceUpdate,
)
from backend.app.services.number_sequence import format_number
from backend.app.services.order_errors import ResourceNotFoundError, VersionConflictError

_MAX_RESERVATION_ATTEMPTS = 10

_DEFAULT_SEQUENCES = {
    "material": {"prefix": "MAT", "pattern": "{PREFIX}-{#####}", "next_value": 1, "reset_policy": "none"},
    "spool": {"prefix": "SP", "pattern": "{PREFIX}-{#####}", "next_value": 1, "reset_policy": "none"},
    "purchase_order": {"prefix": "BE", "pattern": "{PREFIX}-{YYYY}-{#####}", "next_value": 1, "reset_policy": "yearly"},
    "goods_receipt": {"prefix": "WE", "pattern": "{PREFIX}-{YYYY}-{#####}", "next_value": 1, "reset_policy": "yearly"},
}


async def list_number_sequences(session: AsyncSession) -> list[WarehouseNumberSequence]:
    result = await session.execute(select(WarehouseNumberSequence).order_by(WarehouseNumberSequence.key))
    return list(result.scalars().all())


async def create_number_sequence(
    session: AsyncSession,
    data: WarehouseNumberSequenceCreate,
) -> WarehouseNumberSequence:
    sequence = WarehouseNumberSequence(
        **data.model_dump(),
        current_period=None,
    )
    session.add(sequence)
    await session.flush()
    return sequence


async def update_number_sequence(
    session: AsyncSession,
    sequence_id: int,
    data: WarehouseNumberSequenceUpdate,
) -> WarehouseNumberSequence:
    values = data.model_dump(exclude={"version"})
    if data.reset_policy == "none":
        values["current_period"] = None
    result = await session.execute(
        update(WarehouseNumberSequence)
        .where(
            WarehouseNumberSequence.id == sequence_id,
            WarehouseNumberSequence.version == data.version,
        )
        .values(**values, version=WarehouseNumberSequence.version + 1)
        .returning(WarehouseNumberSequence.id)
    )
    if result.scalar_one_or_none() is None:
        exists = await session.scalar(
            select(WarehouseNumberSequence.id).where(WarehouseNumberSequence.id == sequence_id)
        )
        if exists is None:
            raise ResourceNotFoundError(f"Warehouse number sequence {sequence_id} was not found")
        raise VersionConflictError(f"Warehouse number sequence {sequence_id} changed concurrently; reload it and retry")
    sequence = await session.scalar(select(WarehouseNumberSequence).where(WarehouseNumberSequence.id == sequence_id))
    assert sequence is not None
    return sequence


def _period_for_date(effective_date: date, *, reset_policy: str) -> str | None:
    if reset_policy == "yearly":
        return f"{effective_date.year:04d}"
    return None


async def _get_or_create_default_sequence(session: AsyncSession, key: str) -> WarehouseNumberSequence:
    sequence = await session.scalar(select(WarehouseNumberSequence).where(WarehouseNumberSequence.key == key))
    if sequence is not None:
        return sequence

    defaults = _DEFAULT_SEQUENCES.get(key)
    if defaults is None:
        raise ResourceNotFoundError(f"Warehouse number sequence '{key}' was not found")

    try:
        async with session.begin_nested():
            sequence = WarehouseNumberSequence(key=key, **defaults, current_period=None)
            session.add(sequence)
            await session.flush()
            return sequence
    except IntegrityError:
        sequence = await session.scalar(select(WarehouseNumberSequence).where(WarehouseNumberSequence.key == key))
        if sequence is not None:
            return sequence
        raise


async def reserve_number(
    session: AsyncSession,
    *,
    key: str,
    effective_date: date | None = None,
) -> str:
    sequence = await _get_or_create_default_sequence(session, key)
    effective = effective_date or date.today()

    for attempt in range(_MAX_RESERVATION_ATTEMPTS):
        period = _period_for_date(effective, reset_policy=sequence.reset_policy)
        if sequence.reset_policy == "yearly":
            if sequence.current_period != period:
                reserved_value = 1
            else:
                reserved_value = sequence.next_value
        else:
            reserved_value = sequence.next_value

        statement = (
            update(WarehouseNumberSequence)
            .where(
                WarehouseNumberSequence.id == sequence.id,
                WarehouseNumberSequence.version == sequence.version,
            )
            .values(
                next_value=reserved_value + 1,
                current_period=period,
                version=WarehouseNumberSequence.version + 1,
            )
            .returning(WarehouseNumberSequence.id)
        )
        update_result = await session.execute(statement)
        if update_result.scalar_one_or_none() is not None:
            return format_number(
                pattern=sequence.pattern,
                prefix=sequence.prefix,
                value=reserved_value,
                effective_date=effective,
            )

        session.expire(sequence)
        if attempt < _MAX_RESERVATION_ATTEMPTS - 1:
            await session.refresh(sequence)

    raise VersionConflictError(f"Could not reserve warehouse number for key '{key}'")
