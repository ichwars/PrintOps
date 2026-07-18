from sqlalchemy import inspect


EXPECTED_TABLES = {
    "small_part_categories",
    "small_part_units",
    "small_parts",
    "small_part_ledger_entries",
}


async def test_small_parts_schema_contract(test_engine):
    def inspect_schema(sync_connection):
        inspector = inspect(sync_connection)
        tables = set(inspector.get_table_names())
        checks = {
            constraint["name"]
            for table_name in EXPECTED_TABLES
            if table_name in tables
            for constraint in inspector.get_check_constraints(table_name)
        }
        return tables, checks

    async with test_engine.connect() as connection:
        tables, checks = await connection.run_sync(inspect_schema)

    assert tables >= EXPECTED_TABLES
    assert checks >= {
        "ck_small_part_unit_precision",
        "ck_small_part_min_stock",
        "ck_small_part_unit_cost",
        "ck_small_part_ledger_nonzero",
        "ck_small_part_ledger_kind",
    }
