from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.user import User
from backend.app.schemas.procurement import (
    FilamentResource,
    MaterialResource,
    ProcurementOfferRead,
    ProcurementOffersReplace,
    SupplierCreate,
    SupplierListResponse,
    SupplierRead,
    SupplierUpdate,
)
from backend.app.services import procurement as service
from backend.app.services.order_errors import ResourceInUseError

router = APIRouter(tags=["procurement"])


def _conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": "conflict", "message": message})


@router.get("/suppliers", response_model=SupplierListResponse)
async def list_suppliers(
    q: str = "",
    active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> SupplierListResponse:
    page = await service.list_suppliers(db, q=q, active=active, limit=limit, offset=offset)
    return SupplierListResponse(
        items=[SupplierRead.model_validate(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/suppliers", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE),
) -> SupplierRead:
    try:
        supplier = await service.create_supplier(db, data)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Supplier name is already in use") from exc
    await db.refresh(supplier)
    return SupplierRead.model_validate(supplier)


@router.get("/suppliers/{supplier_id}", response_model=SupplierRead)
async def get_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> SupplierRead:
    supplier = await service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return SupplierRead.model_validate(supplier)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierRead)
async def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
) -> SupplierRead:
    try:
        supplier = await service.update_supplier(db, supplier_id, data)
        if supplier is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Supplier not found")
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Supplier name is already in use") from exc
    await db.refresh(supplier)
    return SupplierRead.model_validate(supplier)


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_DELETE),
) -> Response:
    try:
        deleted = await service.delete_supplier(db, supplier_id)
        if not deleted:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Supplier not found")
        await db.commit()
    except ResourceInUseError as exc:
        await db.rollback()
        raise _conflict(str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Supplier is referenced by procurement offers") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _resource_from_query(
    *,
    kind: Literal["material", "filament"],
    small_part_id: int | None,
    material: str | None,
    subtype: str | None,
    brand: str | None,
    color_name: str | None,
) -> MaterialResource | FilamentResource:
    if kind == "material":
        if small_part_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="small_part_id is required")
        return MaterialResource(kind="material", small_part_id=small_part_id)
    if material is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="material is required")
    return FilamentResource(
        kind="filament",
        material=material,
        subtype=subtype,
        brand=brand,
        color_name=color_name,
    )


def _offer_read(result: service.ProcurementOfferResult) -> ProcurementOfferRead:
    offer = result.offer
    return ProcurementOfferRead(
        **{column.name: getattr(offer, column.name) for column in offer.__table__.columns},
        supplier=SupplierRead.model_validate(result.supplier),
    )


@router.get("/procurement-offers", response_model=list[ProcurementOfferRead])
async def list_procurement_offers(
    kind: Literal["material", "filament"],
    small_part_id: int | None = Query(default=None, gt=0),
    material: str | None = None,
    subtype: str | None = None,
    brand: str | None = None,
    color_name: str | None = None,
    active: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> list[ProcurementOfferRead]:
    resource = _resource_from_query(
        kind=kind,
        small_part_id=small_part_id,
        material=material,
        subtype=subtype,
        brand=brand,
        color_name=color_name,
    )
    try:
        results = await service.list_offers(db, resource, active=active)
    except service.ProcurementResourceNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [_offer_read(result) for result in results]


@router.put("/procurement-offers/resource", response_model=list[ProcurementOfferRead])
async def replace_procurement_offers(
    data: ProcurementOffersReplace,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
) -> list[ProcurementOfferRead]:
    try:
        results = await service.replace_offers(db, data.resource, data.offers)
        await db.commit()
    except service.ProcurementResourceNotFound as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.InvalidProcurementReplacement as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Procurement offers violate a resource constraint",
        ) from exc
    return [_offer_read(result) for result in results]


@router.delete(
    "/procurement-offers/{offer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_procurement_offer(
    offer_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_DELETE),
) -> Response:
    if not await service.deactivate_offer(db, offer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Procurement offer not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
