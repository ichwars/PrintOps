from decimal import Decimal

import pytest

from backend.app.services.calculation_engine import (
    CalculationInputError,
    LaborCostInput,
    VariantCostInputs,
    apply_price_method,
    apply_price_rounding,
    calculate_variant,
    required_runs,
)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("none", "12.01"),
        ("0.05", "12.05"),
        ("0.10", "12.10"),
        ("0.50", "12.50"),
        ("1.00", "13.00"),
        ("x.90", "12.90"),
        ("x.99", "12.99"),
    ],
)
def test_price_rounding_modes(mode, expected):
    assert apply_price_rounding(Decimal("12.01"), mode) == Decimal(expected)


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


def test_variant_cost_exposes_risk_discount_tax_contribution_and_unit_price():
    result = calculate_variant(
        VariantCostInputs(
            good_parts=4,
            parts_per_run=2,
            material_grams_per_run=Decimal("100"),
            material_price_per_kg=Decimal("20"),
            additional_costs=Decimal("6"),
            risk_rate=Decimal("0.10"),
            price_method="explicit_price",
            explicit_price=Decimal("40"),
            discount_rate=Decimal("0.10"),
            shipping=Decimal("5"),
            tax_rate=Decimal("0.19"),
        )
    )

    assert result.material_cost == Decimal("4.00")
    assert result.additional_costs == Decimal("6.00")
    assert result.risk_cost == Decimal("1.00")
    assert result.production_cost == Decimal("11.00")
    assert result.net_price == Decimal("41.00")
    assert result.contribution == Decimal("25.00")
    assert result.effective_margin == Decimal("0.694444")
    assert result.tax == Decimal("7.79")
    assert result.gross_price == Decimal("48.79")
    assert result.unit_price == Decimal("10.25")
