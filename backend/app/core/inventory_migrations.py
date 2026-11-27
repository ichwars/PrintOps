from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncConnection


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
