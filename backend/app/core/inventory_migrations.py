from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


async def migrate_inventory_fields(
    conn: AsyncConnection, safe_execute: Callable[[AsyncConnection, str], Awaitable[None]]
) -> None:
    """Add inventory fields to existing spool, material and warehouse tables."""
    await safe_execute(
        conn,
        "ALTER TABLE small_parts ADD COLUMN default_consumption_reason VARCHAR(120) NOT NULL DEFAULT 'Produktion'",
    )
    await safe_execute(conn, "ALTER TABLE small_parts ADD COLUMN internal_notes TEXT")

    stock_check_type = "TIMESTAMP WITH TIME ZONE" if conn.dialect.name == "postgresql" else "DATETIME"
    await safe_execute(conn, f"ALTER TABLE spool ADD COLUMN stock_checked_at {stock_check_type}")
    await safe_execute(conn, f"ALTER TABLE small_parts ADD COLUMN stock_checked_at {stock_check_type}")
    await safe_execute(conn, f"ALTER TABLE warehouse_articles ADD COLUMN stock_checked_at {stock_check_type}")

    for table, column in (
        ("spool", "spool_number"),
        ("small_part_ledger_entries", "receipt_number"),
        ("warehouse_article_ledger_entries", "receipt_number"),
    ):
        await safe_execute(conn, f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR(100)")
        await conn.exec_driver_sql(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column})")

    await safe_execute(
        conn,
        "ALTER TABLE warehouse_purchase_orders ADD COLUMN small_part_id INTEGER "
        "REFERENCES small_parts(id) ON DELETE SET NULL",
    )
    await conn.exec_driver_sql(
        "UPDATE warehouse_purchase_orders SET small_part_id = "
        "(SELECT small_part_id FROM warehouse_shopping_list_items "
        "WHERE id = warehouse_purchase_orders.shopping_item_id) "
        "WHERE small_part_id IS NULL AND shopping_item_id IS NOT NULL"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_small_part_ledger_reference "
        "ON small_part_ledger_entries (reference_type, reference_id)"
    )


async def backfill_inventory_data(session: AsyncSession) -> None:
    from backend.app.services.filament_sku_identity import backfill_material_numbers
    from backend.app.services.warehouse_shopping_list import remove_completed_shopping_items

    await backfill_material_numbers(session)
    await remove_completed_shopping_items(session)
