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

        await connection.execute(
            text(
                "INSERT INTO small_part_units (code, label, decimal_places, is_active) "
                "VALUES ('LEG', 'Legacy unit', 2, 1)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO small_parts "
                "(id, sku, name, description, search_terms, category_id, unit_code, "
                "location_id, minimum_stock, unit_cost, supplier_reference, is_active) "
                "VALUES (401, 'LEGACY-MAT', 'Legacy material', 'Original description', "
                "'old search terms', NULL, 'LEG', NULL, 7.5, 0.25, 'OLD-SUP-42', 1)"
            )
        )
        legacy_columns = (
            "id, sku, name, description, search_terms, category_id, unit_code, location_id, "
            "minimum_stock, unit_cost, supplier_reference, is_active, created_at, updated_at"
        )
        original_row = dict(
            (
                await connection.execute(
                    text(f"SELECT {legacy_columns} FROM small_parts WHERE id = 401")
                )
            )
            .mappings()
            .one()
        )

        await run_migrations(connection)
        await run_migrations(connection)

        columns = await column_names(connection, "small_parts")
        assert {"default_consumption_reason", "internal_notes"} <= columns
        assert "opening_quantity" not in columns
        migrated_row = (
            (
                await connection.execute(
                    text(
                        f"SELECT {legacy_columns}, default_consumption_reason, internal_notes "
                        "FROM small_parts WHERE id = 401"
                    )
                )
            )
            .mappings()
            .one()
        )
        assert {key: migrated_row[key] for key in original_row} == original_row
        assert migrated_row["default_consumption_reason"] == "Produktion"
        assert migrated_row["internal_notes"] is None
