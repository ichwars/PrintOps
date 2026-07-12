from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
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
    additional_costs: Decimal = Decimal("0")
    risk_rate: Decimal = Decimal("0")
    shipping: Decimal = Decimal("0")
    price_method: Literal["markup", "target_margin", "explicit_price"] = "target_margin"
    price_rate: Decimal = Decimal("0")
    explicit_price: Decimal = Decimal("0")
    discount_rate: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("0")
    minimum_price: Decimal = Decimal("0")
    minimum_profit: Decimal = Decimal("0")
    rounding_mode: Literal["none", "0.05", "0.10", "0.50", "1.00", "x.90", "x.99"] = "none"


@dataclass(frozen=True)
class VariantCostResult:
    total_runs: int
    material_cost: Decimal
    machine_cost: Decimal
    energy_cost: Decimal
    labor_cost: Decimal
    consumables: Decimal
    packaging: Decimal
    additional_costs: Decimal
    risk_cost: Decimal
    production_cost: Decimal
    shipping: Decimal
    selling_price: Decimal
    net_price: Decimal
    contribution: Decimal
    effective_margin: Decimal
    tax: Decimal
    gross_price: Decimal
    unit_price: Decimal


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
    if method == "explicit_price":
        return round_money(rate)
    raise CalculationInputError("unknown price method")


def apply_price_rounding(value: Decimal, mode: str) -> Decimal:
    if mode == "none":
        return round_money(value)
    if mode in {"0.05", "0.10", "0.50", "1.00"}:
        increment = Decimal(mode)
        return ((value / increment).to_integral_value(rounding=ROUND_CEILING) * increment).quantize(MONEY)
    if mode in {"x.90", "x.99"}:
        ending = Decimal("0.90") if mode == "x.90" else Decimal("0.99")
        whole = value.to_integral_value(rounding=ROUND_CEILING)
        candidate = whole - Decimal("1") + ending
        if candidate < value:
            candidate += Decimal("1")
        return candidate.quantize(MONEY)
    raise CalculationInputError("unknown price rounding mode")


def calculate_variant(inputs: VariantCostInputs) -> VariantCostResult:
    if inputs.scrap_runs < 0 or any(
        value < 0
        for value in (
            inputs.additional_costs,
            inputs.risk_rate,
            inputs.explicit_price,
            inputs.discount_rate,
            inputs.tax_rate,
        )
    ):
        raise CalculationInputError("cost, rate, and scrap inputs must not be negative")
    if inputs.discount_rate >= 1:
        raise CalculationInputError("discount rate must be below one")
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
    base_production = (
        material
        + machine
        + energy
        + labor
        + inputs.consumables
        + inputs.packaging
        + inputs.additional_costs
    )
    risk = base_production * inputs.risk_rate
    production = base_production + risk
    derived = (
        round_money(inputs.explicit_price)
        if inputs.price_method == "explicit_price"
        else apply_price_method(production, inputs.price_method, inputs.price_rate)
    )
    before_shipping = max(derived, inputs.minimum_price, production + inputs.minimum_profit)
    discounted = before_shipping * (Decimal("1") - inputs.discount_rate)
    net = apply_price_rounding(discounted + inputs.shipping, inputs.rounding_mode)
    contribution = round_money(discounted - production)
    margin = (
        Decimal("0")
        if discounted <= 0
        else (contribution / round_money(discounted)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    )
    tax = round_money(net * inputs.tax_rate)
    gross = round_money(net + tax)
    unit = round_money(net / Decimal(inputs.good_parts)) if inputs.good_parts > 0 else Decimal("0.00")
    return VariantCostResult(
        total_runs=runs,
        material_cost=round_money(material),
        machine_cost=round_money(machine),
        energy_cost=round_money(energy),
        labor_cost=round_money(labor),
        consumables=round_money(inputs.consumables),
        packaging=round_money(inputs.packaging),
        additional_costs=round_money(inputs.additional_costs),
        risk_cost=round_money(risk),
        production_cost=round_money(production),
        shipping=round_money(inputs.shipping),
        selling_price=net,
        net_price=net,
        contribution=contribution,
        effective_margin=margin,
        tax=tax,
        gross_price=gross,
        unit_price=unit,
    )
