from dataclasses import dataclass, replace
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
    material_markup_rate: Decimal = Decimal("0")
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
    additive_materials: Decimal = Decimal("0")
    scrap_rate: Decimal = Decimal("0")
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
    material_markup: Decimal
    machine_cost: Decimal
    energy_cost: Decimal
    labor_cost: Decimal
    consumables: Decimal
    packaging: Decimal
    additional_costs: Decimal
    additive_materials: Decimal
    scrap_cost: Decimal
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
    breakdown: tuple["CalculationCostBreakdownItem", ...]


@dataclass(frozen=True)
class CalculationCostBreakdownItem:
    code: str
    label: str
    basis: str
    amount: Decimal


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
            inputs.additive_materials,
            inputs.material_markup_rate,
            inputs.scrap_rate,
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
    raw_material = inputs.material_grams_per_run * Decimal(runs) / Decimal("1000") * inputs.material_price_per_kg
    material_markup = raw_material * inputs.material_markup_rate
    material = raw_material + material_markup
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
        + inputs.additive_materials
    )
    scrap = base_production * inputs.scrap_rate
    risk = base_production * inputs.risk_rate
    production = base_production + scrap + risk
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
        material_markup=round_money(material_markup),
        machine_cost=round_money(machine),
        energy_cost=round_money(energy),
        labor_cost=round_money(labor),
        consumables=round_money(inputs.consumables),
        packaging=round_money(inputs.packaging),
        additional_costs=round_money(inputs.additional_costs),
        additive_materials=round_money(inputs.additive_materials),
        scrap_cost=round_money(scrap),
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
        breakdown=(
            CalculationCostBreakdownItem("machine", "Machine", f"{runs} runs", round_money(machine)),
            CalculationCostBreakdownItem("labor", "Labor", "allocated time", round_money(labor)),
            CalculationCostBreakdownItem("material", "Material", f"{runs} runs", round_money(material)),
            CalculationCostBreakdownItem("energy", "Energy", "printer and dryer", round_money(energy)),
            CalculationCostBreakdownItem(
                "additive_materials", "Additional materials", "line items", round_money(inputs.additive_materials)
            ),
            CalculationCostBreakdownItem("consumables", "Consumables", "flat amount", round_money(inputs.consumables)),
            CalculationCostBreakdownItem("scrap", "Scrap", f"{inputs.scrap_rate * 100}%", round_money(scrap)),
            CalculationCostBreakdownItem("risk", "Risk", f"{inputs.risk_rate * 100}%", round_money(risk)),
            CalculationCostBreakdownItem("packaging", "Packaging", "flat amount", round_money(inputs.packaging)),
            CalculationCostBreakdownItem("shipping", "Shipping", "flat amount", round_money(inputs.shipping)),
        ),
    )


def calculate_combined(operations: list[VariantCostInputs], commercial: VariantCostInputs) -> VariantCostResult:
    if not operations:
        raise CalculationInputError("at least one operation is required")
    results = [calculate_variant(operation) for operation in operations]
    material = sum((item.material_cost for item in results), Decimal("0"))
    machine = sum((item.machine_cost for item in results), Decimal("0"))
    energy = sum((item.energy_cost for item in results), Decimal("0"))
    labor = sum((item.labor_cost for item in results), Decimal("0"))
    material_markup = sum((item.material_markup for item in results), Decimal("0"))
    combined = calculate_variant(
        replace(
            commercial,
            material_grams_per_run=Decimal("0"),
            material_price_per_kg=Decimal("0"),
            print_hours_per_run=Decimal("0"),
            machine_cost_per_hour=Decimal("0"),
            printer_power_kw=Decimal("0"),
            drying_hours=Decimal("0"),
            dryer_power_kw=Decimal("0"),
            labor=(),
            additional_costs=commercial.additional_costs + material + machine + energy + labor,
        )
    )
    return replace(
        combined,
        total_runs=sum(item.total_runs for item in results),
        material_cost=material,
        machine_cost=machine,
        energy_cost=energy,
        labor_cost=labor,
        material_markup=material_markup,
        additional_costs=round_money(commercial.additional_costs),
        breakdown=tuple(
            item
            for code in ("machine", "labor", "material", "energy")
            for item in (
                CalculationCostBreakdownItem(
                    code,
                    code.replace("_", " ").title(),
                    "all operations",
                    round_money(sum((getattr(result, f"{code}_cost") for result in results), Decimal("0"))),
                ),
            )
        )
        + tuple(item for item in combined.breakdown if item.code not in {"machine", "labor", "material", "energy"}),
    )
