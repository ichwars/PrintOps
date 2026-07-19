from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from backend.app.core.database import run_migrations


async def column_names(connection, table_name: str) -> set[str]:
    return await connection.run_sync(
        lambda sync_connection: {
            column["name"] for column in inspect(sync_connection).get_columns(table_name)
        }
    )


@pytest.mark.asyncio
async def test_material_procurement_columns_migrate_idempotently(test_engine):
    async with test_engine.begin() as connection:
        existing_columns = await column_names(connection, "small_parts")
        for column_name in ("default_consumption_reason", "internal_notes"):
            if column_name in existing_columns:
                await connection.execute(text(f"ALTER TABLE small_parts DROP COLUMN {column_name}"))

        await run_migrations(connection)
        await run_migrations(connection)

        columns = await column_names(connection, "small_parts")
        assert {"default_consumption_reason", "internal_notes"} <= columns
        assert "opening_quantity" not in columns
