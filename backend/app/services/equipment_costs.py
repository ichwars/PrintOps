from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def _anniversary(start: date, year: int) -> date:
    try:
        return start.replace(year=year)
    except ValueError:
        return start.replace(year=year, day=28)


def calculate_residual_value(
    acquisition_value: Decimal,
    acquisition_date: date,
    service_years: Decimal,
    as_of: date | None = None,
) -> Decimal:
    if acquisition_value < 0 or service_years <= 0:
        raise ValueError("acquisition value must be non-negative and service life must be positive")
    current = as_of or date.today()
    if current <= acquisition_date:
        elapsed_years = Decimal("0")
    else:
        completed_years = current.year - acquisition_date.year
        anniversary = _anniversary(acquisition_date, acquisition_date.year + completed_years)
        if anniversary > current:
            completed_years -= 1
            anniversary = _anniversary(acquisition_date, acquisition_date.year + completed_years)
        next_anniversary = _anniversary(acquisition_date, acquisition_date.year + completed_years + 1)
        year_fraction = Decimal((current - anniversary).days) / Decimal((next_anniversary - anniversary).days)
        elapsed_years = Decimal(completed_years) + year_fraction
    remaining_ratio = max(Decimal("0"), Decimal("1") - elapsed_years / service_years)
    return (acquisition_value * remaining_ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_hourly_rate(
    acquisition_value: Decimal,
    service_years: Decimal,
    annual_hours: Decimal,
    maintenance_rate: Decimal,
) -> Decimal:
    if acquisition_value < 0 or service_years <= 0 or annual_hours <= 0 or maintenance_rate < 0:
        raise ValueError("device cost inputs are outside the supported range")
    return (acquisition_value / (service_years * annual_hours) * (Decimal("1") + maintenance_rate)).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
