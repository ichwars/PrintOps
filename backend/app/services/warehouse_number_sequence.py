from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.warehouse_number_sequence import WarehouseNumberSequence
from backend.app.schemas.warehouse_number_sequence import (
    WarehouseNumberSequenceCreate,
    WarehouseNumberSequenceUpdate,
)
from backend.app.services.order_errors import ResourceNotFoundError, VersionConflictError


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
        raise VersionConflictError(
            f"Warehouse number sequence {sequence_id} changed concurrently; reload it and retry"
        )
    sequence = await session.scalar(
        select(WarehouseNumberSequence).where(WarehouseNumberSequence.id == sequence_id)
    )
    assert sequence is not None
    return sequence
