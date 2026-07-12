from decimal import Decimal

import pytest

from backend.app.services.calculation_engine import (
    CalculationInputError,
    LaborCostInput,
    VariantCostInputs,
    apply_price_method,
    calculate_variant,
    required_runs,
)


@pytest.mark.parametrize(("good_parts", "per_run", "expected"), [(10, 4, 3), (8, 4, 2)])
def test_required_runs_uses_ceiling(good_parts, per_run, expected):
    assert required_runs(good_parts, per_run) == expected


def test_required_runs_rejects_zero_parts_per_run():
    with pytest.raises(CalculationInputError, match="parts_per_run"):
        required_runs(1, 0)


def test_target_margin_differs_from_markup():
    cost = Decimal("100")
    assert apply_price_method(cost, "markup", Decimal("0.35")) == Decimal("135.00")
    assert apply_price_method(cost, "target_margin", Decimal("0.35")) == Decimal("153.85")


def test_variant_cost_keeps_shipping_separate_and_allocates_labor():
    result = calculate_variant(
        VariantCostInputs(
            good_parts=10,
            parts_per_run=4,
            scrap_runs=1,
            material_grams_per_run=Decimal("100"),
            material_price_per_kg=Decimal("20"),
            print_hours_per_run=Decimal("2"),
            machine_cost_per_hour=Decimal("1.50"),
            printer_power_kw=Decimal("0.2"),
            electricity_price_per_kwh=Decimal("0.30"),
            labor=(
                LaborCostInput(Decimal("0.5"), Decimal("20"), "request"),
                LaborCostInput(Decimal("0.1"), Decimal("20"), "run"),
                LaborCostInput(Decimal("0.05"), Decimal("20"), "unit"),
            ),
            consumables=Decimal("1"),
            packaging=Decimal("2"),
            shipping=Decimal("5"),
            price_method="markup",
            price_rate=Decimal("0.25"),
        )
    )

    assert result.total_runs == 4
    assert result.material_cost == Decimal("8.00")
    assert result.machine_cost == Decimal("12.00")
    assert result.energy_cost == Decimal("0.48")
    assert result.labor_cost == Decimal("28.00")
    assert result.production_cost == Decimal("51.48")
    assert result.shipping == Decimal("5.00")
    assert result.selling_price == Decimal("69.35")
