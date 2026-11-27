from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.procurement import WarehouseShoppingListItem
from backend.app.models.small_part import SmallPart, SmallPartUnit
from backend.app.schemas.procurement import WarehouseShoppingItemRead
from backend.app.services import small_parts
from backend.app.services.warehouse_articles import MAX_QUANTITY, WarehouseError


def read_item(item: WarehouseShoppingListItem) -> WarehouseShoppingItemRead:
    assert item.small_part_id is not None
    return WarehouseShoppingItemRead(
        id=item.id,
        resource_kind="material",
        resource_id=item.small_part_id,
        sku=item.sku,
        name=item.name,
        quantity=item.quantity,
        unit_code=item.unit_code,
        unit_label=item.unit_label,
    )


async def add_item(db: AsyncSession, material_id: int) -> WarehouseShoppingListItem:
    material = await db.get(SmallPart, material_id)
    if material is None or not material.is_active:
        raise WarehouseError("not_found", "Active material not found", 404)
    item = WarehouseShoppingListItem
    existing = await db.scalar(select(item).where(item.small_part_id == material.id))
    if existing is not None:
        return existing

    available = (await small_parts.get_balance(db, material.id)).available
    quantity = material.minimum_stock - available
    if quantity <= 0 or quantity > MAX_QUANTITY:
        raise WarehouseError("no_reorder_quantity", "Stock does not have a valid reorder quantity")
    unit = await db.get(SmallPartUnit, material.unit_code)
    if unit is None:
        raise WarehouseError("stock_unit_missing", "Stock unit not found")

    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else postgres_insert
    # The unique stock-owner column serializes adds from concurrent browsers.
    # Return the first entry on conflict without replacing its saved quantity or unit.
    return (
        await db.scalars(
            insert(item)
            .values(
                {
                    "small_part_id": material.id,
                    "sku": material.sku,
                    "name": material.name,
                    "quantity": quantity,
                    "unit_code": unit.code,
                    "unit_label": unit.label,
                }
            )
            .on_conflict_do_update(index_elements=[item.small_part_id], set_={"quantity": item.quantity})
            .returning(item)
        )
    ).one()
