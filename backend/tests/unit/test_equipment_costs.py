from datetime import date
from decimal import Decimal

import pytest

from backend.app.services.equipment_costs import calculate_hourly_rate, calculate_residual_value


def test_residual_value_uses_straight_line_depreciation():
    assert calculate_residual_value(Decimal("1200"), date(2025, 1, 1), Decimal("4"), date(2025, 1, 1)) == Decimal("1200.00")
    assert calculate_residual_value(Decimal("1200"), date(2024, 1, 1), Decimal("4"), date(2026, 1, 1)) == Decimal("600.00")
    assert calculate_residual_value(Decimal("1200"), date(2020, 1, 1), Decimal("4"), date(2026, 1, 1)) == Decimal("0.00")


def test_hourly_rate_includes_maintenance_and_wear():
    assert calculate_hourly_rate(Decimal("1200"), Decimal("4"), Decimal("1000"), Decimal("0.25")) == Decimal("0.375000")


@pytest.mark.parametrize("years,hours", [(Decimal("0"), Decimal("1000")), (Decimal("4"), Decimal("0"))])
def test_hourly_rate_rejects_invalid_capacity(years, hours):
    with pytest.raises(ValueError):
        calculate_hourly_rate(Decimal("1200"), years, hours, Decimal("0"))
