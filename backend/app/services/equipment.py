from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.equipment import Equipment
from backend.app.schemas.equipment import EquipmentCreate, EquipmentUpdate


async def list_equipment(db: AsyncSession, *, active_only: bool = False) -> list[Equipment]:
    query = select(Equipment).order_by(Equipment.name, Equipment.id)
    if active_only:
        query = query.where(Equipment.is_active.is_(True))
    return list((await db.execute(query)).scalars().all())


async def get_equipment(db: AsyncSession, equipment_id: int) -> Equipment | None:
    return await db.get(Equipment, equipment_id)


async def create_equipment(db: AsyncSession, data: EquipmentCreate) -> Equipment:
    equipment = Equipment(**data.model_dump())
    db.add(equipment)
    await db.flush()
    await db.refresh(equipment)
    return equipment


async def update_equipment(db: AsyncSession, equipment: Equipment, data: EquipmentUpdate) -> Equipment:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(equipment, key, value)
    await db.flush()
    await db.refresh(equipment)
    return equipment
