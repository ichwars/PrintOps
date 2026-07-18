from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.user import User
from backend.app.schemas.commerce import OrderRead, ReservationCommand, ReservationQuantityCommand
from backend.app.services import stock_reservations
from backend.app.services.order_errors import OrderDomainError, ResourceNotFoundError

router = APIRouter(prefix="/orders", tags=["orders"])


def _raise(error: OrderDomainError):
    code = status.HTTP_404_NOT_FOUND if isinstance(error, ResourceNotFoundError) else status.HTTP_409_CONFLICT
    detail_code = "not_found" if isinstance(error, ResourceNotFoundError) else "invalid_reservation_state"
    raise HTTPException(code, detail={"code": detail_code, "message": str(error)})


@router.get("", response_model=list[OrderRead])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDERS_READ),
) -> list[OrderRead]:
    return [OrderRead.model_validate(item) for item in await stock_reservations.list_orders(db)]


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDERS_READ),
) -> OrderRead:
    try:
        return OrderRead.model_validate(await stock_reservations.get_order(db, order_id))
    except OrderDomainError as exc:
        _raise(exc)


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(
    order_id: int,
    data: ReservationCommand,
    db: AsyncSession = Depends(get_db),
    user: User | None = RequirePermissionIfAuthEnabled(Permission.ORDERS_CANCEL),
) -> OrderRead:
    try:
        order = await stock_reservations.release_order(
            db, order_id=order_id, idempotency_key=data.idempotency_key, actor_id=user.id if user else None
        )
        await db.commit()
    except OrderDomainError as exc:
        await db.rollback()
        _raise(exc)
    return OrderRead.model_validate(order)


@router.post("/{order_id}/small-parts/{allocation_id}/issue", response_model=OrderRead)
async def issue_small_part(
    order_id: int,
    allocation_id: int,
    data: ReservationQuantityCommand,
    db: AsyncSession = Depends(get_db),
    user: User | None = RequirePermissionIfAuthEnabled(Permission.ORDERS_MANAGE_PRODUCTION),
) -> OrderRead:
    try:
        order = await stock_reservations.issue_small_part(
            db,
            order_id=order_id,
            allocation_id=allocation_id,
            quantity=data.quantity,
            idempotency_key=data.idempotency_key,
            actor_id=user.id if user else None,
        )
        await db.commit()
    except OrderDomainError as exc:
        await db.rollback()
        _raise(exc)
    return OrderRead.model_validate(order)


@router.post("/{order_id}/filament/{allocation_id}/reconcile", response_model=OrderRead)
async def reconcile_filament(
    order_id: int,
    allocation_id: int,
    data: ReservationQuantityCommand,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDERS_MANAGE_PRODUCTION),
) -> OrderRead:
    try:
        order = await stock_reservations.reconcile_filament(
            db,
            order_id=order_id,
            allocation_id=allocation_id,
            quantity=data.quantity,
            idempotency_key=data.idempotency_key,
        )
        await db.commit()
    except OrderDomainError as exc:
        await db.rollback()
        _raise(exc)
    return OrderRead.model_validate(order)
