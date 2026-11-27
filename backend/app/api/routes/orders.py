from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled, allowed_printer_ids_for_user, resolve_optional_api_key
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.user import User
from backend.app.schemas.commerce import (
    CommercialAmountsRead,
    OrderDetailRead,
    OrderRead,
    ReservationCommand,
    ReservationQuantityCommand,
)
from backend.app.services import stock_reservations
from backend.app.services.document_recipients import document_recipient, resolve_recipient_names
from backend.app.services.order_errors import OrderDomainError, ResourceNotFoundError

router = APIRouter(prefix="/orders", tags=["orders"])


def _raise(error: OrderDomainError) -> NoReturn:
    code = status.HTTP_404_NOT_FOUND if isinstance(error, ResourceNotFoundError) else status.HTTP_409_CONFLICT
    detail_code = "not_found" if isinstance(error, ResourceNotFoundError) else "invalid_reservation_state"
    raise HTTPException(code, detail={"code": detail_code, "message": str(error)})


@router.get("", response_model=list[OrderRead])
async def list_orders(
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDERS_READ),
) -> list[OrderRead]:
    return [OrderRead.model_validate(item) for item in await stock_reservations.list_orders(db)]


@router.get("/{order_id}", response_model=OrderDetailRead)
async def get_order(
    order_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDERS_READ),
) -> OrderDetailRead:
    try:
        order = await stock_reservations.get_order(db, order_id)
    except OrderDomainError as exc:
        _raise(exc)

    confirmation = next(
        (
            document
            for document in order.commercial_documents
            if document.document_type == "order_confirmation"
            and document.number == order.number
            and document.business_profile_id == order.business_profile_id
        ),
        None,
    )
    recipient = document_recipient(confirmation) if confirmation is not None else order.customer_id
    names = await resolve_recipient_names(db, {order.id: recipient})
    return OrderDetailRead(
        **OrderRead.model_validate(order).model_dump(),
        customer_display_name=names[order.id],
        confirmation=CommercialAmountsRead.model_validate(confirmation) if confirmation is not None else None,
    )


@router.get("/{order_id}/production")
async def order_production(
    order_id: int,
    db: AsyncSession = DB_SESSION,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.ORDERS_READ),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
):
    """Confirmed parts only; shipping, order status and stock stay independent."""
    from backend.app.services.print_confirmation import confirmed_production

    try:
        order = await stock_reservations.get_order(db, order_id)
    except OrderDomainError as exc:
        _raise(exc)
    return await confirmed_production(
        db, order.project_id, printer_ids=api_key.printer_ids if api_key else allowed_printer_ids_for_user(user)
    )


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(
    order_id: int,
    data: ReservationCommand,
    db: AsyncSession = DB_SESSION,
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
    db: AsyncSession = DB_SESSION,
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
    db: AsyncSession = DB_SESSION,
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
