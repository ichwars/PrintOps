from decimal import Decimal

from sqlalchemy import Numeric, inspect

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.calculation import Calculation, CalculationRevision, CalculationVariant
from backend.app.schemas.calculation import CalculationCreate


def test_calculation_accepts_all_visible_labor_overrides():
    payload = {
        "business_profile_id": 1,
        "title": "Configured labor",
        "currency": "EUR",
        "commercial_overrides": {
            "setup_hours": "0.5",
            "post_processing_hours_per_unit": "0.25",
            "cad_hours": "1.5",
            "qa_hours": "0.1",
            "labor_rate": "42",
        },
        "variants": [{"name": "Standard", "is_preferred": True}],
    }

    calculation = CalculationCreate.model_validate(payload)

    assert calculation.commercial_overrides["cad_hours"] == Decimal("1.5")


async def test_calculation_supports_request_without_customer(db_session):
    profile = BusinessProfile(
        name="Calculation issuer",
        legal_name="Calculation issuer GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()

    calculation = Calculation(business_profile_id=profile.id, title="Four brackets")
    calculation.variants.append(CalculationVariant(name="Standard", is_preferred=True))
    db_session.add(calculation)
    await db_session.flush()

    assert calculation.customer_id is None
    assert calculation.version == 1
    assert calculation.status == "draft"
    assert calculation.variants[0].is_preferred is True


async def test_calculation_revision_uses_decimal_totals(db_session):
    profile = BusinessProfile(
        name="Revision issuer",
        legal_name="Revision issuer GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    calculation = Calculation(business_profile_id=profile.id, title="Revision")
    db_session.add(calculation)
    await db_session.flush()

    revision = CalculationRevision(
        calculation_id=calculation.id,
        revision_number=1,
        snapshot={"currency": "EUR"},
        production_cost=Decimal("12.34"),
        selling_price=Decimal("18.99"),
        currency="EUR",
    )
    db_session.add(revision)
    await db_session.flush()

    assert revision.production_cost == Decimal("12.34")
    assert isinstance(CalculationRevision.__table__.c.production_cost.type, Numeric)


async def test_calculation_tables_are_registered(test_engine):
    async with test_engine.connect() as connection:
        tables = await connection.run_sync(lambda conn: set(inspect(conn).get_table_names()))

    assert {
        "calculations",
        "calculation_variants",
        "calculation_lines",
        "calculation_operations",
        "calculation_labors",
        "calculation_revisions",
        "calculation_templates",
    } <= tables
