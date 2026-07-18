from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.commerce import CustomerOrder
from backend.app.models.spool import Spool
from backend.app.models.stock_reservation import (
    StockReservation,
    StockReservationAllocation,
    StockReservationCommand,
)
from backend.app.services.order_errors import ResourceInUseError, ResourceNotFoundError
from backend.app.services.small_parts import append_ledger_entry

_ORDER_LOAD = (
    selectinload(CustomerOrder.reservations)
    .selectinload(StockReservation.allocations)
    .selectinload(StockReservationAllocation.small_part),
    selectinload(CustomerOrder.reservations)
    .selectinload(StockReservation.allocations)
    .selectinload(StockReservationAllocation.spool),
)


async def get_order(session: AsyncSession, order_id: int, *, lock: bool = False) -> CustomerOrder:
    statement = select(CustomerOrder).where(CustomerOrder.id == order_id).options(*_ORDER_LOAD)
    if lock:
        statement = statement.with_for_update()
    order = await session.scalar(statement)
    if order is None:
        raise ResourceNotFoundError(f"Order {order_id} was not found")
    return order


async def list_orders(session: AsyncSession) -> list[CustomerOrder]:
    return list(
        (
            await session.scalars(select(CustomerOrder).options(*_ORDER_LOAD).order_by(CustomerOrder.created_at.desc()))
        ).unique()
    )


async def _replay(session: AsyncSession, order_id: int, key: str) -> CustomerOrder | None:
    command = await session.scalar(
        select(StockReservationCommand).where(StockReservationCommand.idempotency_key == key)
    )
    if command is None:
        return None
    if command.order_id != order_id:
        raise ResourceInUseError("Idempotency key belongs to a different order")
    return await get_order(session, order_id)


async def _allocation(
    session: AsyncSession, order_id: int, allocation_id: int, *, lock: bool = True
) -> tuple[StockReservation, StockReservationAllocation]:
    statement = (
        select(StockReservationAllocation)
        .join(StockReservation, StockReservation.id == StockReservationAllocation.reservation_id)
        .where(
            StockReservationAllocation.id == allocation_id,
            StockReservation.order_id == order_id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    allocation = await session.scalar(statement)
    if allocation is None:
        raise ResourceNotFoundError(f"Allocation {allocation_id} was not found")
    reservation = await session.get(StockReservation, allocation.reservation_id)
    return reservation, allocation


async def issue_small_part(
    session: AsyncSession,
    *,
    order_id: int,
    allocation_id: int,
    quantity: Decimal,
    idempotency_key: str,
    actor_id: int | None,
) -> CustomerOrder:
    replay = await _replay(session, order_id, idempotency_key)
    if replay is not None:
        return replay
    order = await get_order(session, order_id, lock=True)
    if order.status != "active":
        raise ResourceInUseError("Only an active order can issue small parts")
    reservation, allocation = await _allocation(session, order_id, allocation_id)
    if allocation.small_part_id is None or reservation.status != "active":
        raise ResourceInUseError("Allocation is not an active small-part reservation")
    outstanding = allocation.allocated_quantity - allocation.consumed_quantity
    if quantity <= 0 or quantity > outstanding:
        raise ResourceInUseError(f"Issue quantity exceeds reserved remainder {outstanding}")
    await append_ledger_entry(
        session,
        small_part_id=allocation.small_part_id,
        entry_kind="issue",
        physical_delta=-quantity,
        reserved_delta=-quantity,
        reason=f"Issued to order {order.number}",
        reference_type="customer_order",
        reference_id=order.id,
        actor_id=actor_id,
        idempotency_key=f"issue:{idempotency_key}",
    )
    allocation.consumed_quantity += quantity
    if allocation.consumed_quantity == allocation.allocated_quantity:
        reservation.status = "consumed"
    session.add(
        StockReservationCommand(
            order_id=order.id,
            allocation_id=allocation.id,
            command="issue",
            quantity=quantity,
            idempotency_key=idempotency_key,
        )
    )
    await session.flush()
    return await get_order(session, order.id)


async def reconcile_filament(
    session: AsyncSession,
    *,
    order_id: int,
    allocation_id: int,
    quantity: Decimal,
    idempotency_key: str,
) -> CustomerOrder:
    replay = await _replay(session, order_id, idempotency_key)
    if replay is not None:
        return replay
    order = await get_order(session, order_id, lock=True)
    if order.status != "active":
        raise ResourceInUseError("Only an active order can reconcile filament")
    reservation, allocation = await _allocation(session, order_id, allocation_id)
    if allocation.spool_id is None or reservation.status != "active":
        raise ResourceInUseError("Allocation is not an active internal filament reservation")
    if quantity <= 0:
        raise ResourceInUseError("Actual filament quantity must be positive")
    spool = await session.scalar(select(Spool).where(Spool.id == allocation.spool_id).with_for_update())
    if spool is None:
        raise ResourceNotFoundError(f"Spool {allocation.spool_id} was not found")
    spool.weight_used = float(Decimal(str(spool.weight_used or 0)) + quantity)
    allocation.consumed_quantity = min(allocation.allocated_quantity, quantity)
    reservation.status = "consumed"
    reservation.released_at = datetime.now(timezone.utc)
    session.add(
        StockReservationCommand(
            order_id=order.id,
            allocation_id=allocation.id,
            command="reconcile",
            quantity=quantity,
            idempotency_key=idempotency_key,
        )
    )
    await session.flush()
    return await get_order(session, order.id)


async def release_order(
    session: AsyncSession,
    *,
    order_id: int,
    idempotency_key: str,
    actor_id: int | None,
) -> CustomerOrder:
    replay = await _replay(session, order_id, idempotency_key)
    if replay is not None:
        return replay
    order = await get_order(session, order_id, lock=True)
    if order.status != "active":
        raise ResourceInUseError("Only an active order can be cancelled")
    now = datetime.now(timezone.utc)
    for reservation in order.reservations:
        if reservation.status != "active":
            continue
        for allocation in reservation.allocations:
            outstanding = allocation.allocated_quantity - allocation.consumed_quantity
            if allocation.small_part_id is not None and outstanding > 0:
                await append_ledger_entry(
                    session,
                    small_part_id=allocation.small_part_id,
                    entry_kind="release",
                    physical_delta=0,
                    reserved_delta=-outstanding,
                    reason=f"Released by cancellation of order {order.number}",
                    reference_type="customer_order",
                    reference_id=order.id,
                    actor_id=actor_id,
                    idempotency_key=f"release:{idempotency_key}:{allocation.id}",
                )
        reservation.status = "released"
        reservation.released_at = now
    order.status = "cancelled"
    session.add(
        StockReservationCommand(
            order_id=order.id,
            allocation_id=None,
            command="cancel",
            quantity=0,
            idempotency_key=idempotency_key,
        )
    )
    await session.flush()
    return await get_order(session, order.id)
