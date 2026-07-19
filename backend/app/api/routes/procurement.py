from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.user import User
from backend.app.schemas.procurement import SupplierCreate, SupplierListResponse, SupplierRead, SupplierUpdate
from backend.app.services import procurement as service
from backend.app.services.order_errors import ResourceInUseError

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": "conflict", "message": message})


@router.get("", response_model=SupplierListResponse)
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


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
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


@router.get("/{supplier_id}", response_model=SupplierRead)
async def get_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> SupplierRead:
    supplier = await service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return SupplierRead.model_validate(supplier)


@router.patch("/{supplier_id}", response_model=SupplierRead)
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


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
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
