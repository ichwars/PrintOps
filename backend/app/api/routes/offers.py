from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.user import User
from backend.app.schemas.commerce import (
    AcceptanceRead,
    OfferAccept,
    OfferCreate,
    OfferRead,
    OrderRead,
    VersionedTransition,
)
from backend.app.services import offers as offer_service
from backend.app.services.order_errors import OrderDomainError, ResourceNotFoundError, VersionConflictError
from backend.app.services.stock_availability import InsufficientStock

router = APIRouter(prefix="/offers", tags=["offers"])


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, ResourceNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": str(error)})
    if isinstance(error, VersionConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, detail={"code": "version_conflict", "message": str(error)})
    if isinstance(error, InsufficientStock):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "reservation_blocked",
                "message": str(error),
                "shortages": [
                    {
                        "source_key": line.requirement.source_key,
                        "description": line.requirement.description,
                        "required": str(line.requirement.quantity),
                        "available": str(line.available),
                        "shortage": str(line.shortage),
                    }
                    for line in error.lines
                ],
            },
        )
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": "invalid_offer_state", "message": str(error)})


@router.get("", response_model=list[OfferRead])
async def list_offers(
    offer_status: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_READ),
) -> list[OfferRead]:
    return [OfferRead.model_validate(item) for item in await offer_service.list_offers(db, offer_status)]


@router.post("", response_model=OfferRead, status_code=status.HTTP_201_CREATED)
async def create_offer(
    data: OfferCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_DRAFT),
) -> OfferRead:
    try:
        offer = await offer_service.create_offer(db, data.calculation_revision_id)
        await db.commit()
    except (OrderDomainError, ValueError) as exc:
        await db.rollback()
        raise _http_error(exc)
    return OfferRead.model_validate(offer)


@router.get("/{offer_id}", response_model=OfferRead)
async def get_offer(
    offer_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_READ),
) -> OfferRead:
    try:
        return OfferRead.model_validate(await offer_service.get_offer(db, offer_id))
    except OrderDomainError as exc:
        raise _http_error(exc)


async def _transition(db: AsyncSession, offer_id: int, data: VersionedTransition, target: str) -> OfferRead:
    try:
        offer = await offer_service.transition_offer(db, offer_id, target, data.expected_version)
        await db.commit()
    except OrderDomainError as exc:
        await db.rollback()
        raise _http_error(exc)
    return OfferRead.model_validate(offer)


@router.post("/{offer_id}/send", response_model=OfferRead)
async def send_offer(
    offer_id: int,
    data: VersionedTransition,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_ISSUE),
) -> OfferRead:
    return await _transition(db, offer_id, data, "sent")


@router.post("/{offer_id}/reject", response_model=OfferRead)
async def reject_offer(
    offer_id: int,
    data: VersionedTransition,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_CORRECT),
) -> OfferRead:
    return await _transition(db, offer_id, data, "rejected")


@router.post("/{offer_id}/accept", response_model=AcceptanceRead)
async def accept_offer(
    offer_id: int,
    data: OfferAccept,
    db: AsyncSession = Depends(get_db),
    user: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_APPROVE),
) -> AcceptanceRead:
    try:
        result = await offer_service.accept_offer(
            db,
            offer_id=offer_id,
            expected_version=data.expected_version,
            idempotency_key=data.idempotency_key,
            actor_id=user.id if user else None,
        )
        await db.commit()
    except (OrderDomainError, InsufficientStock, ValueError) as exc:
        await db.rollback()
        raise _http_error(exc)
    return AcceptanceRead(
        offer=OfferRead.model_validate(result.offer),
        order=OrderRead.model_validate(result.order),
        project_id=result.project.id,
    )
