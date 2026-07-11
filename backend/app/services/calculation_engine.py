from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

MONEY = Decimal("0.01")


class CalculationInputError(ValueError):
    pass


@dataclass(frozen=True)
class LaborCostInput:
    hours: Decimal
    hourly_rate: Decimal
    allocation_basis: Literal["request", "run", "unit"]


@dataclass(frozen=True)
class VariantCostInputs:
    good_parts: int
    parts_per_run: int
    scrap_runs: int = 0
    material_grams_per_run: Decimal = Decimal("0")
    material_price_per_kg: Decimal = Decimal("0")
    print_hours_per_run: Decimal = Decimal("0")
    machine_cost_per_hour: Decimal = Decimal("0")
    printer_power_kw: Decimal = Decimal("0")
    electricity_price_per_kwh: Decimal = Decimal("0")
    drying_hours: Decimal = Decimal("0")
    dryer_power_kw: Decimal = Decimal("0")
    labor: tuple[LaborCostInput, ...] = ()
    consumables: Decimal = Decimal("0")
    packaging: Decimal = Decimal("0")
    shipping: Decimal = Decimal("0")
    price_method: Literal["markup", "target_margin"] = "target_margin"
    price_rate: Decimal = Decimal("0")
    minimum_price: Decimal = Decimal("0")
    minimum_profit: Decimal = Decimal("0")


@dataclass(frozen=True)
class VariantCostResult:
    total_runs: int
    material_cost: Decimal
    machine_cost: Decimal
    energy_cost: Decimal
    labor_cost: Decimal
    production_cost: Decimal
    shipping: Decimal
    selling_price: Decimal


def round_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def required_runs(good_parts: int, parts_per_run: int) -> int:
    if good_parts < 0:
        raise CalculationInputError("good_parts must not be negative")
    if parts_per_run <= 0:
        raise CalculationInputError("parts_per_run must be positive")
    return (good_parts + parts_per_run - 1) // parts_per_run


def apply_price_method(cost: Decimal, method: str, rate: Decimal) -> Decimal:
    if cost < 0 or rate < 0:
        raise CalculationInputError("cost and rate must not be negative")
    if method == "markup":
        return round_money(cost * (Decimal("1") + rate))
    if method == "target_margin":
        if rate >= Decimal("1"):
            raise CalculationInputError("target margin must be below one")
        return round_money(cost / (Decimal("1") - rate))
    raise CalculationInputError("unknown price method")


def calculate_variant(inputs: VariantCostInputs) -> VariantCostResult:
    if inputs.scrap_runs < 0:
        raise CalculationInputError("scrap_runs must not be negative")
    runs = required_runs(inputs.good_parts, inputs.parts_per_run) + inputs.scrap_runs
    material = inputs.material_grams_per_run * Decimal(runs) / Decimal("1000") * inputs.material_price_per_kg
    machine = inputs.print_hours_per_run * Decimal(runs) * inputs.machine_cost_per_hour
    energy = (
        inputs.print_hours_per_run * Decimal(runs) * inputs.printer_power_kw
        + inputs.drying_hours * inputs.dryer_power_kw
    ) * inputs.electricity_price_per_kwh
    labor = Decimal("0")
    for entry in inputs.labor:
        multiplier = Decimal("1")
        if entry.allocation_basis == "run":
            multiplier = Decimal(runs)
        elif entry.allocation_basis == "unit":
            multiplier = Decimal(inputs.good_parts)
        elif entry.allocation_basis != "request":
            raise CalculationInputError("unknown labor allocation basis")
        labor += entry.hours * entry.hourly_rate * multiplier
    production = material + machine + energy + labor + inputs.consumables + inputs.packaging
    derived = apply_price_method(production, inputs.price_method, inputs.price_rate)
    selling = max(derived, inputs.minimum_price, production + inputs.minimum_profit) + inputs.shipping
    return VariantCostResult(
        total_runs=runs,
        material_cost=round_money(material),
        machine_cost=round_money(machine),
        energy_cost=round_money(energy),
        labor_cost=round_money(labor),
        production_cost=round_money(production),
        shipping=round_money(inputs.shipping),
        selling_price=round_money(selling),
    )
