from sqlalchemy import inspect


async def test_procurement_schema_contract(test_engine):
    def inspect_schema(sync_connection):
        inspector = inspect(sync_connection)
        return (
            set(inspector.get_table_names()),
            {item["name"] for item in inspector.get_check_constraints("procurement_offers")},
            {item["name"] for item in inspector.get_indexes("procurement_offers")},
            {
                tuple(item["constrained_columns"]): item["options"].get("ondelete")
                for item in inspector.get_foreign_keys("procurement_offers")
            },
        )

    async with test_engine.connect() as connection:
        tables, checks, indexes, foreign_key_actions = await connection.run_sync(inspect_schema)

    assert {"suppliers", "procurement_offers"} <= tables
    assert {"ck_procurement_offer_target", "ck_procurement_offer_values"} <= checks
    assert "uq_procurement_offer_preferred_resource" in indexes
    assert foreign_key_actions[("small_part_id",)] == "RESTRICT"
    assert foreign_key_actions[("filament_sku_settings_id",)] == "RESTRICT"
