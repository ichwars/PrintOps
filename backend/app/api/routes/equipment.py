from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.user import User
from backend.app.schemas.equipment import EquipmentCreate, EquipmentRead, EquipmentUpdate
from backend.app.services import equipment as equipment_service

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("/", response_model=list[EquipmentRead])
async def list_equipment(
    active_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
) -> list[EquipmentRead]:
    return [
        EquipmentRead.model_validate(item)
        for item in await equipment_service.list_equipment(db, active_only=active_only)
    ]


@router.post("/", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    data: EquipmentCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
) -> EquipmentRead:
    item = await equipment_service.create_equipment(db, data)
    await db.commit()
    return EquipmentRead.model_validate(item)


@router.put("/{equipment_id}", response_model=EquipmentRead)
async def update_equipment(
    equipment_id: int,
    data: EquipmentUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
) -> EquipmentRead:
    item = await equipment_service.get_equipment(db, equipment_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Equipment not found")
    item = await equipment_service.update_equipment(db, item, data)
    await db.commit()
    return EquipmentRead.model_validate(item)


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment(
    equipment_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
) -> None:
    item = await equipment_service.get_equipment(db, equipment_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Equipment not found")
    await db.delete(item)
    await db.commit()
