from sqlalchemy import inspect

from backend.app.models.calculation_project import CalculationVariantPlate

EXPECTED_TABLES = {
    "calculation_project_files",
    "calculation_project_plates",
    "calculation_variant_plates",
    "calculation_variant_small_parts",
}


def test_variant_plate_uniqueness_contract():
    names = {constraint.name for constraint in CalculationVariantPlate.__table__.constraints}
    assert "uq_calculation_variant_plate" in names
    assert "ck_calculation_variant_plate_counts" in names


async def test_calculation_project_schema_contract(test_engine):
    def inspect_schema(connection):
        inspector = inspect(connection)
        return set(inspector.get_table_names())

    async with test_engine.connect() as connection:
        tables = await connection.run_sync(inspect_schema)

    assert tables >= EXPECTED_TABLES
