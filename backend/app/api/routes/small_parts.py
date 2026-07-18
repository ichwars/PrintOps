from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.core.websocket import ws_manager
from backend.app.models.small_part import SmallPart, SmallPartCategory, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.user import User
from backend.app.schemas.small_part import (
    SmallPartCategoryCreate,
    SmallPartCategoryRead,
    SmallPartCategoryUpdate,
    SmallPartCreate,
    SmallPartLedgerCreate,
    SmallPartLedgerRead,
    SmallPartListResponse,
    SmallPartOptionRead,
    SmallPartRead,
    SmallPartUnitCreate,
    SmallPartUnitRead,
    SmallPartUnitUpdate,
    SmallPartUpdate,
)
from backend.app.services import small_parts as service

router = APIRouter(prefix="/small-parts", tags=["small-parts"])


async def _load_part(db: AsyncSession, small_part_id: int) -> SmallPart:
    part = await db.scalar(
        select(SmallPart)
        .where(SmallPart.id == small_part_id)
        .options(selectinload(SmallPart.category), selectinload(SmallPart.unit), selectinload(SmallPart.location))
    )
    if part is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Kleinteil fehlt"})
    return part


async def _read_part(db: AsyncSession, part: SmallPart) -> SmallPartRead:
    balance = await service.get_balance(db, part.id)
    return SmallPartRead.model_validate(
        {
            "id": part.id,
            "sku": part.sku,
            "name": part.name,
            "description": part.description,
            "search_terms": part.search_terms,
            "category_id": part.category_id,
            "unit_code": part.unit_code,
            "location_id": part.location_id,
            "minimum_stock": part.minimum_stock,
            "unit_cost": part.unit_cost,
            "supplier_reference": part.supplier_reference,
            "is_active": part.is_active,
            "category": part.category,
            "unit": part.unit,
            "balance": {
                "physical": balance.physical,
                "reserved": balance.reserved,
                "available": balance.available,
                "is_low_stock": balance.available <= part.minimum_stock,
            },
            "created_at": part.created_at,
            "updated_at": part.updated_at,
        }
    )


def _conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": "conflict", "message": message})


@router.get("/search", response_model=list[SmallPartOptionRead])
async def search_small_part_options(
    q: str = "",
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> list[SmallPartOptionRead]:
    matches = await service.search_small_parts(db, query=q, active_only=True, limit=limit)
    return [
        SmallPartOptionRead(
            id=item.part.id,
            sku=item.part.sku,
            name=item.part.name,
            unit_code=item.part.unit_code,
            unit_cost=item.part.unit_cost,
            available=item.available,
        )
        for item in matches
    ]


@router.get("/settings/categories", response_model=list[SmallPartCategoryRead])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    return list(await db.scalars(select(SmallPartCategory).order_by(SmallPartCategory.name)))


@router.post("/settings/categories", response_model=SmallPartCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: SmallPartCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE),
):
    category = SmallPartCategory(name=data.name, name_key=data.name.strip().casefold(), is_active=data.is_active)
    db.add(category)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Kategorie ist bereits vorhanden") from exc
    await db.refresh(category)
    return category


@router.patch("/settings/categories/{category_id}", response_model=SmallPartCategoryRead)
async def update_category(
    category_id: int,
    data: SmallPartCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    category = await db.get(SmallPartCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        category.name_key = changes["name"].strip().casefold()
    for field, value in changes.items():
        setattr(category, field, value)
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/settings/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_DELETE),
):
    category = await db.get(SmallPartCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    if await db.scalar(select(func.count(SmallPart.id)).where(SmallPart.category_id == category_id)):
        raise _conflict("Kategorie wird noch verwendet")
    await db.delete(category)
    await db.commit()


@router.get("/settings/units", response_model=list[SmallPartUnitRead])
async def list_units(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    return list(await db.scalars(select(SmallPartUnit).order_by(SmallPartUnit.label)))


@router.post("/settings/units", response_model=SmallPartUnitRead, status_code=status.HTTP_201_CREATED)
async def create_unit(
    data: SmallPartUnitCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE),
):
    unit = SmallPartUnit(**data.model_dump())
    db.add(unit)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Einheit ist bereits vorhanden") from exc
    await db.refresh(unit)
    return unit


@router.patch("/settings/units/{unit_code}", response_model=SmallPartUnitRead)
async def update_unit(
    unit_code: str,
    data: SmallPartUnitUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    unit = await db.get(SmallPartUnit, unit_code.upper())
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unit not found")
    referenced = await db.scalar(select(func.count(SmallPart.id)).where(SmallPart.unit_code == unit.code))
    changes = data.model_dump(exclude_unset=True)
    if referenced and "decimal_places" in changes and changes["decimal_places"] != unit.decimal_places:
        raise _conflict("Nach Verwendung kann die Genauigkeit nicht mehr geändert werden")
    for field, value in changes.items():
        setattr(unit, field, value)
    await db.commit()
    await db.refresh(unit)
    return unit


@router.delete("/settings/units/{unit_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unit(
    unit_code: str,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_DELETE),
):
    unit = await db.get(SmallPartUnit, unit_code.upper())
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unit not found")
    if await db.scalar(select(func.count(SmallPart.id)).where(SmallPart.unit_code == unit.code)):
        raise _conflict("Einheit wird noch verwendet")
    await db.delete(unit)
    await db.commit()


@router.get("", response_model=SmallPartListResponse)
async def list_small_parts(
    q: str = "",
    active: bool | None = None,
    low_stock: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> SmallPartListResponse:
    matches = await service.search_small_parts(db, query=q, active_only=active is not False, limit=10000)
    if active is not None:
        matches = [item for item in matches if item.part.is_active is active]
    reads = [await _read_part(db, item.part) for item in matches]
    if low_stock:
        reads = [item for item in reads if item.balance.is_low_stock]
    total = len(reads)
    return SmallPartListResponse(items=reads[offset : offset + limit], total=total, limit=limit, offset=offset)


@router.post("", response_model=SmallPartRead, status_code=status.HTTP_201_CREATED)
async def create_small_part(
    data: SmallPartCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE),
) -> SmallPartRead:
    part = SmallPart(**data.model_dump())
    db.add(part)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Artikelnummer ist bereits vorhanden oder ein Katalogwert fehlt") from exc
    return await _read_part(db, await _load_part(db, part.id))


@router.get("/{small_part_id}", response_model=SmallPartRead)
async def get_small_part(
    small_part_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> SmallPartRead:
    return await _read_part(db, await _load_part(db, small_part_id))


@router.patch("/{small_part_id}", response_model=SmallPartRead)
async def update_small_part(
    small_part_id: int,
    data: SmallPartUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
) -> SmallPartRead:
    part = await _load_part(db, small_part_id)
    try:
        await service.update_small_part(db, part, data)
        await db.commit()
    except service.SmallPartUnitChangeNotAllowed as exc:
        await db.rollback()
        raise _conflict(str(exc)) from exc
    return await _read_part(db, await _load_part(db, small_part_id))


@router.get("/{small_part_id}/ledger", response_model=list[SmallPartLedgerRead])
async def list_small_part_ledger(
    small_part_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    await _load_part(db, small_part_id)
    return list(
        await db.scalars(
            select(SmallPartLedgerEntry)
            .where(SmallPartLedgerEntry.small_part_id == small_part_id)
            .order_by(SmallPartLedgerEntry.created_at.desc(), SmallPartLedgerEntry.id.desc())
        )
    )


@router.post("/{small_part_id}/ledger", response_model=SmallPartLedgerRead, status_code=status.HTTP_201_CREATED)
async def add_small_part_stock(
    small_part_id: int,
    data: SmallPartLedgerCreate,
    db: AsyncSession = Depends(get_db),
    user: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
) -> SmallPartLedgerRead:
    try:
        entry = await service.append_ledger_entry(
            db,
            small_part_id=small_part_id,
            entry_kind=data.entry_kind,
            physical_delta=data.quantity,
            reserved_delta=Decimal("0"),
            reason=data.reason,
            idempotency_key=data.idempotency_key,
            actor_id=user.id if user else None,
        )
        await db.commit()
    except service.SmallPartNotFound as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": str(exc)}) from exc
    except service.InsufficientSmallPartStock as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "insufficient_stock", "message": str(exc)},
        ) from exc
    await db.refresh(entry)
    await ws_manager.broadcast({"type": "inventory_changed", "resource": "small_part", "id": small_part_id})
    return SmallPartLedgerRead.model_validate(entry)
