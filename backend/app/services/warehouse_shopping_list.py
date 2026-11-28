from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.procurement import (
    WarehousePurchaseOrder,
    WarehouseShoppingListItem,
)
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
from backend.app.schemas.procurement import (
    WarehousePurchaseOrderRead,
    WarehousePurchaseOrderReceiptCreate,
    WarehousePurchaseOrderReceiptHistoryRow,
    WarehousePurchaseOrderReceiptRead,
    WarehouseShoppingItemRead,
)
from backend.app.services import procurement, small_parts
from backend.app.services.warehouse_articles import (
    MAX_QUANTITY,
    WarehouseError,
    check_precision,
)
from backend.app.services.warehouse_number_sequence import reserve_number

PURCHASE_ORDER_REFERENCE = "warehouse_purchase_order"


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


async def create_purchase_order(db: AsyncSession, item_id: int) -> WarehousePurchaseOrder:
    await db.execute(
        update(WarehouseShoppingListItem)
        .where(WarehouseShoppingListItem.id == item_id)
        .values(id=WarehouseShoppingListItem.id)
    )
    item = await db.get(WarehouseShoppingListItem, item_id)
    if item is None or item.small_part_id is None:
        raise WarehouseError("not_found", "Shopping list item not found", 404)
    existing = await db.scalar(select(WarehousePurchaseOrder).where(WarehousePurchaseOrder.shopping_item_id == item_id))
    if existing is not None:
        return existing
    material = await db.get(SmallPart, item.small_part_id)
    if material is None or not material.is_active:
        raise WarehouseError("not_found", "Active material not found", 404)
    offers = await procurement.preferred_offers_for_materials(db, [item.small_part_id])
    preferred = offers.get(item.small_part_id)
    supplier = preferred.supplier if preferred and preferred.supplier.is_active else None
    order = WarehousePurchaseOrder(
        number=await reserve_number(db, key="purchase_order"),
        shopping_item_id=item.id,
        small_part_id=material.id,
        supplier_id=supplier.id if supplier else None,
        supplier_name=supplier.name if supplier else None,
        sku=item.sku,
        name=item.name,
        quantity=item.quantity,
        unit_code=item.unit_code,
        unit_label=item.unit_label,
    )
    db.add(order)
    await db.flush()
    return order


async def list_purchase_orders(db: AsyncSession, *, order_id: int | None = None) -> list[WarehousePurchaseOrderRead]:
    receipts = (
        select(
            SmallPartLedgerEntry.reference_id.label("order_id"),
            func.sum(SmallPartLedgerEntry.physical_delta).label("received"),
        )
        .where(
            SmallPartLedgerEntry.reference_type == PURCHASE_ORDER_REFERENCE,
            SmallPartLedgerEntry.entry_kind == "receipt",
        )
        .group_by(SmallPartLedgerEntry.reference_id)
        .subquery()
    )
    statement = (
        select(WarehousePurchaseOrder, receipts.c.received, SmallPart, SmallPartUnit)
        .outerjoin(receipts, receipts.c.order_id == WarehousePurchaseOrder.id)
        .outerjoin(SmallPart, SmallPart.id == WarehousePurchaseOrder.small_part_id)
        .outerjoin(SmallPartUnit, SmallPartUnit.code == SmallPart.unit_code)
        .order_by(WarehousePurchaseOrder.id.desc())
    )
    if order_id is not None:
        statement = statement.where(WarehousePurchaseOrder.id == order_id)
    return [
        WarehousePurchaseOrderRead.model_validate(order).model_copy(
            update={
                "received_quantity": received or Decimal("0"),
                "open_quantity": order.quantity - (received or Decimal("0")),
                "can_receive": bool(
                    material
                    and material.is_active
                    and material.unit_code == order.unit_code
                    and unit
                    and unit.is_active
                    and order.quantity > (received or Decimal("0"))
                ),
            }
        )
        for order, received, material, unit in (await db.execute(statement)).all()
    ]


async def remove_completed_shopping_items(
    db: AsyncSession, orders: list[WarehousePurchaseOrderRead] | None = None
) -> None:
    if orders is None:
        orders = await list_purchase_orders(db)
    item_ids = [
        order.shopping_item_id for order in orders if order.open_quantity == 0 and order.shopping_item_id is not None
    ]
    if item_ids:
        await db.execute(
            update(WarehouseShoppingListItem)
            .where(WarehouseShoppingListItem.id.in_(item_ids))
            .values(id=WarehouseShoppingListItem.id)
        )
        await db.execute(
            update(WarehousePurchaseOrder)
            .where(WarehousePurchaseOrder.shopping_item_id.in_(item_ids))
            .values(shopping_item_id=None)
        )
        await db.execute(delete(WarehouseShoppingListItem).where(WarehouseShoppingListItem.id.in_(item_ids)))


async def list_order_receipts(db: AsyncSession, order_id: int) -> list[WarehousePurchaseOrderReceiptHistoryRow]:
    if await db.get(WarehousePurchaseOrder, order_id) is None:
        raise WarehouseError("not_found", "Purchase order not found", 404)
    entries = await db.execute(
        select(
            SmallPartLedgerEntry.id,
            SmallPartLedgerEntry.receipt_number,
            SmallPartLedgerEntry.physical_delta.label("quantity"),
            SmallPartLedgerEntry.created_at,
        )
        .where(
            SmallPartLedgerEntry.reference_type == PURCHASE_ORDER_REFERENCE,
            SmallPartLedgerEntry.reference_id == order_id,
            SmallPartLedgerEntry.entry_kind == "receipt",
        )
        .order_by(SmallPartLedgerEntry.id)
    )
    return [WarehousePurchaseOrderReceiptHistoryRow.model_validate(row) for row in entries.mappings()]


async def receive_purchase_order(
    db: AsyncSession,
    order_id: int,
    data: WarehousePurchaseOrderReceiptCreate,
    *,
    actor_id: int | None,
) -> WarehousePurchaseOrderReceiptRead:
    # Match shopping-list mutations' lock order before checking the remaining quantity.
    # The first write also serializes SQLite writers.
    await db.execute(
        update(WarehouseShoppingListItem)
        .where(
            WarehouseShoppingListItem.id
            == select(WarehousePurchaseOrder.shopping_item_id)
            .where(WarehousePurchaseOrder.id == order_id)
            .scalar_subquery()
        )
        .values(id=WarehouseShoppingListItem.id)
    )
    await db.execute(
        update(WarehousePurchaseOrder).where(WarehousePurchaseOrder.id == order_id).values(id=WarehousePurchaseOrder.id)
    )
    order = await db.get(WarehousePurchaseOrder, order_id)
    if order is None:
        raise WarehouseError("not_found", "Purchase order not found", 404)
    prior = await db.scalar(
        select(SmallPartLedgerEntry).where(SmallPartLedgerEntry.idempotency_key == data.idempotency_key)
    )
    material_id = order.small_part_id
    if material_id is None:
        if prior is None:
            raise WarehouseError("invalid_material", "Purchase order material is unavailable")
        material_id = prior.small_part_id
    if prior is None:
        await db.execute(
            update(SmallPart)
            .where(SmallPart.id == material_id)
            .values(id=SmallPart.id, updated_at=SmallPart.updated_at)
            .execution_options(synchronize_session=False)
        )
        material = await db.get(SmallPart, material_id)
        unit = await db.get(SmallPartUnit, order.unit_code)
        if (
            not material
            or not material.is_active
            or material.unit_code != order.unit_code
            or not unit
            or not unit.is_active
        ):
            raise WarehouseError("invalid_material", "Purchase order material or unit is unavailable")
        check_precision(data.quantity, unit)
        view = (await list_purchase_orders(db, order_id=order_id))[0]
        if data.quantity > view.open_quantity:
            raise WarehouseError("over_receipt", "Quantity exceeds the open purchase order quantity")

    try:
        entry = await small_parts.append_ledger_entry(
            db,
            small_part_id=material_id,
            entry_kind="receipt",
            physical_delta=data.quantity,
            reserved_delta=Decimal("0"),
            reason=order.number,
            idempotency_key=data.idempotency_key,
            reference_type=PURCHASE_ORDER_REFERENCE,
            reference_id=order.id,
            actor_id=actor_id,
            require_active=True,
        )
    except small_parts.SmallPartIdempotencyConflict as exc:
        raise WarehouseError("idempotency_conflict", str(exc)) from exc
    assert entry.receipt_number is not None
    view = (await list_purchase_orders(db, order_id=order_id))[0]
    if view.open_quantity == 0 and view.shopping_item_id is not None:
        await remove_completed_shopping_items(db, [view])
        view = view.model_copy(update={"shopping_item_id": None})
    return WarehousePurchaseOrderReceiptRead(
        receipt_id=entry.id,
        receipt_number=entry.receipt_number,
        order=view,
    )
