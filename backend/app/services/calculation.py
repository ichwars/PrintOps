from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.calculation import (
    Calculation,
    CalculationLabor,
    CalculationLine,
    CalculationOperation,
    CalculationRevision,
    CalculationTemplate,
    CalculationVariant,
)
from backend.app.models.customer import Customer
from backend.app.models.settings import Settings
from backend.app.schemas.calculation import CalculationCreate, CalculationUpdate
from backend.app.services.calculation_engine import LaborCostInput, VariantCostInputs, calculate_combined
from backend.app.services.order_errors import ResourceInUseError, ResourceNotFoundError, VersionConflictError

_LOAD = (
    selectinload(Calculation.variants).selectinload(CalculationVariant.lines),
    selectinload(Calculation.variants)
    .selectinload(CalculationVariant.operations)
    .selectinload(CalculationOperation.labor),
    selectinload(Calculation.revisions),
)


@dataclass(frozen=True)
class CalculationPage:
    rows: list[Calculation]
    total: int
    limit: int
    offset: int


async def _load(session: AsyncSession, calculation_id: int, *, for_update: bool = False) -> Calculation:
    statement = select(Calculation).options(*_LOAD).where(Calculation.id == calculation_id)
    if for_update:
        statement = statement.with_for_update()
    calculation = (await session.execute(statement)).scalar_one_or_none()
    if calculation is None:
        raise ResourceNotFoundError(f"Calculation {calculation_id} was not found")
    return calculation


async def get_calculation(session: AsyncSession, calculation_id: int) -> Calculation:
    return await _load(session, calculation_id)


async def list_calculations(session: AsyncSession, *, status: str | None, limit: int, offset: int) -> CalculationPage:
    predicate = Calculation.status == status if status else True
    total = await session.scalar(select(func.count()).select_from(Calculation).where(predicate)) or 0
    rows = list(
        (
            await session.scalars(
                select(Calculation)
                .options(*_LOAD)
                .where(predicate)
                .order_by(Calculation.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return CalculationPage(rows, total, limit, offset)


async def _validate_references(session: AsyncSession, profile_id: int, customer_id: int | None) -> None:
    profile = await session.get(BusinessProfile, profile_id)
    if profile is None:
        raise ResourceNotFoundError(f"Business profile {profile_id} was not found")
    if not profile.is_active:
        raise ResourceInUseError(f"Business profile {profile_id} is inactive")
    if customer_id is not None and await session.get(Customer, customer_id) is None:
        raise ResourceNotFoundError(f"Customer {customer_id} was not found")


async def _cost_defaults(session: AsyncSession) -> dict:
    rows = (
        await session.execute(
            select(Settings.key, Settings.value).where(
                Settings.key.in_({"calculation_defaults", "default_filament_cost", "energy_cost_per_kwh"})
            )
        )
    ).all()
    stored = dict(rows)
    defaults = {
        "acquisitionValue": 749,
        "serviceYears": 4,
        "annualHours": 1200,
        "maintenancePercent": 25,
        "laborRate": 20,
        "setupHours": 0.3,
        "postProcessingHours": 0.25,
        "qaHours": 0.05,
        "consumables": 0.75,
        "packaging": 2.5,
        "shipping": 5.49,
    }
    try:
        defaults.update(json.loads(stored.get("calculation_defaults", "{}")))
    except (TypeError, ValueError):
        pass
    defaults["materialPricePerKg"] = stored.get("default_filament_cost", "25")
    defaults["electricityPricePerKwh"] = stored.get("energy_cost_per_kwh", "0.15")
    return defaults


def _variant(data) -> CalculationVariant:
    variant = CalculationVariant(
        name=data.name,
        is_preferred=data.is_preferred,
        sort_order=data.sort_order,
        price_method=data.price_method,
        price_rate=data.price_rate,
    )
    variant.lines = [CalculationLine(**line.model_dump()) for line in data.lines]
    for operation_data in data.operations:
        values = operation_data.model_dump(exclude={"labor"})
        operation = CalculationOperation(**values)
        operation.labor = [CalculationLabor(**labor.model_dump()) for labor in operation_data.labor]
        variant.operations.append(operation)
    return variant


async def create_calculation(session: AsyncSession, data: CalculationCreate) -> Calculation:
    await _validate_references(session, data.business_profile_id, data.customer_id)
    calculation = Calculation(**data.model_dump(exclude={"variants"}))
    calculation.variants = [_variant(item) for item in data.variants]
    session.add(calculation)
    await session.flush()
    return await _load(session, calculation.id)


async def update_calculation(session: AsyncSession, calculation_id: int, data: CalculationUpdate) -> Calculation:
    calculation = await _load(session, calculation_id, for_update=True)
    if calculation.status != "draft":
        raise ResourceInUseError("Approved calculations cannot be edited")
    if calculation.version != data.expected_version:
        raise VersionConflictError(f"Calculation {calculation_id} has changed")
    await _validate_references(session, data.business_profile_id, data.customer_id)
    for field in ("business_profile_id", "customer_id", "title", "currency", "notes"):
        setattr(calculation, field, getattr(data, field))
    calculation.variants.clear()
    await session.flush()
    calculation.variants = [_variant(item) for item in data.variants]
    calculation.version += 1
    await session.flush()
    return await _load(session, calculation.id)


def _snapshot(calculation: Calculation, warning_reasons: dict[str, str]) -> dict:
    return {
        "calculation": {
            "id": calculation.id,
            "title": calculation.title,
            "business_profile_id": calculation.business_profile_id,
            "customer_id": calculation.customer_id,
            "currency": calculation.currency,
        },
        "variants": [
            {
                "name": variant.name,
                "is_preferred": variant.is_preferred,
                "price_method": variant.price_method,
                "price_rate": str(variant.price_rate),
                "lines": [
                    {
                        "kind": line.kind,
                        "description": line.description,
                        "quantity": str(line.quantity),
                        "unit_code": line.unit_code,
                        "unit_price": str(line.unit_price) if line.unit_price is not None else None,
                    }
                    for line in variant.lines
                ],
                "operations": [
                    {
                        "kind": operation.kind,
                        "title": operation.title,
                        "good_parts": operation.good_parts,
                        "parts_per_run": operation.parts_per_run,
                        "scrap_runs": operation.scrap_runs,
                        "material_grams_per_run": str(operation.material_grams_per_run),
                        "print_hours_per_run": str(operation.print_hours_per_run),
                        "provenance": operation.provenance,
                    }
                    for operation in variant.operations
                ],
            }
            for variant in calculation.variants
        ],
        "warning_reasons": warning_reasons,
    }


async def approve_calculation(
    session: AsyncSession,
    calculation_id: int,
    expected_version: int,
    warning_reasons: dict[str, str],
    approved_by_id: int | None,
) -> CalculationRevision:
    calculation = await _load(session, calculation_id, for_update=True)
    if calculation.version != expected_version:
        raise VersionConflictError(f"Calculation {calculation_id} has changed")
    preferred = [variant for variant in calculation.variants if variant.is_preferred]
    if len(preferred) != 1:
        raise ResourceInUseError("Exactly one preferred variant is required")
    if not preferred[0].lines:
        raise ResourceInUseError("At least one sellable line is required")
    defaults = await _cost_defaults(session)
    default_labor = (
        LaborCostInput(Decimal(str(defaults["setupHours"])), Decimal(str(defaults["laborRate"])), "request"),
        LaborCostInput(Decimal(str(defaults["postProcessingHours"])), Decimal(str(defaults["laborRate"])), "unit"),
        LaborCostInput(Decimal(str(defaults["qaHours"])), Decimal(str(defaults["laborRate"])), "request"),
    )
    operation_inputs: list[VariantCostInputs] = []
    for operation in preferred[0].operations:
        labor = (
            tuple(LaborCostInput(item.hours, item.hourly_rate, item.allocation_basis) for item in operation.labor)
            or default_labor
        )
        provenance = operation.provenance or {}
        operation_inputs.append(
            VariantCostInputs(
                good_parts=operation.good_parts,
                parts_per_run=operation.parts_per_run,
                scrap_runs=operation.scrap_runs,
                material_grams_per_run=operation.material_grams_per_run,
                material_price_per_kg=Decimal(str(defaults["materialPricePerKg"])),
                print_hours_per_run=operation.print_hours_per_run,
                machine_cost_per_hour=Decimal(str(provenance.get("printer_hourly_rate") or "0")),
                printer_power_kw=Decimal(str(provenance.get("printer_power_watts") or "0")) / Decimal("1000"),
                electricity_price_per_kwh=Decimal(str(defaults["electricityPricePerKwh"])),
                drying_hours=Decimal(str(provenance.get("drying_hours") or "0")),
                dryer_power_kw=Decimal(str(provenance.get("dryer_power_watts") or "0")) / Decimal("1000"),
                labor=labor,
            )
        )
    total_units = max(1, int(sum((line.quantity for line in preferred[0].lines), Decimal("0"))))
    result = calculate_combined(
        operation_inputs,
        VariantCostInputs(
            good_parts=total_units,
            parts_per_run=1,
            consumables=Decimal(str(defaults.get("consumables", 0))),
            packaging=Decimal(str(defaults.get("packaging", 0))),
            additional_costs=Decimal(str(defaults.get("additionalCosts", 0))),
            risk_rate=Decimal(str(defaults.get("riskPercent", 0))) / Decimal("100"),
            shipping=Decimal(str(defaults.get("shipping", 0))),
            price_method=preferred[0].price_method,
            price_rate=Decimal("0") if preferred[0].price_method == "explicit_price" else preferred[0].price_rate,
            explicit_price=preferred[0].price_rate if preferred[0].price_method == "explicit_price" else Decimal(str(defaults.get("explicitPrice", 0))),
            discount_rate=Decimal(str(defaults.get("discountPercent", 0))) / Decimal("100"),
            tax_rate=Decimal(str(defaults.get("taxPercent", 0))) / Decimal("100"),
            minimum_price=Decimal(str(defaults.get("minimumPrice", 0))),
            minimum_profit=Decimal(str(defaults.get("minimumProfit", 0))),
            rounding_mode=str(defaults.get("roundingMode", "none")),
        ),
    )
    revision_number = 1 + max((revision.revision_number for revision in calculation.revisions), default=0)
    snapshot = _snapshot(calculation, warning_reasons)
    snapshot["cost_defaults"] = {key: str(value) for key, value in defaults.items()}
    revision = CalculationRevision(
        calculation_id=calculation.id,
        revision_number=revision_number,
        snapshot=snapshot,
        production_cost=result.production_cost,
        selling_price=result.net_price,
        currency=calculation.currency,
        approved_by_id=approved_by_id,
    )
    session.add(revision)
    calculation.status = "approved"
    calculation.version += 1
    await session.flush()
    return revision


async def archive_calculation(session: AsyncSession, calculation_id: int, expected_version: int) -> Calculation:
    calculation = await _load(session, calculation_id, for_update=True)
    if calculation.version != expected_version:
        raise VersionConflictError(f"Calculation {calculation_id} has changed")
    calculation.status = "archived"
    calculation.version += 1
    await session.flush()
    return calculation


async def create_template(session: AsyncSession, calculation_id: int, name: str) -> CalculationTemplate:
    calculation = await _load(session, calculation_id)
    definition = _snapshot(calculation, {})
    definition["calculation"].pop("customer_id", None)
    template = CalculationTemplate(
        business_profile_id=calculation.business_profile_id, name=name, definition=definition
    )
    session.add(template)
    await session.flush()
    return template


async def list_templates(session: AsyncSession) -> list[CalculationTemplate]:
    return list((await session.scalars(select(CalculationTemplate).order_by(CalculationTemplate.name, CalculationTemplate.id))).all())


async def instantiate_template(session: AsyncSession, template_id: int, title: str, customer_id: int | None) -> Calculation:
    template = await session.get(CalculationTemplate, template_id)
    if template is None:
        raise ResourceNotFoundError(f"Calculation template {template_id} was not found")
    definition = template.definition
    calculation_data = definition["calculation"]
    await _validate_references(session, template.business_profile_id, customer_id)
    calculation = Calculation(business_profile_id=template.business_profile_id, customer_id=customer_id, title=title, currency=calculation_data.get("currency", "EUR"), notes=None)
    for variant_index, source_variant in enumerate(definition.get("variants", [])):
        variant = CalculationVariant(name=source_variant["name"], is_preferred=source_variant.get("is_preferred", variant_index == 0), sort_order=variant_index, price_method=source_variant.get("price_method", "target_margin"), price_rate=Decimal(str(source_variant.get("price_rate", "0"))))
        variant.lines = [CalculationLine(kind=line.get("kind", "printed_part"), description=line.get("description", ""), quantity=Decimal(str(line.get("quantity", "1"))), unit_code=line.get("unit_code", "C62"), unit_price=Decimal(str(line["unit_price"])) if line.get("unit_price") is not None else None, sort_order=index) for index, line in enumerate(source_variant.get("lines", []))]
        variant.operations = [CalculationOperation(kind=operation.get("kind", "printing"), title=operation.get("title", ""), source_file=None, source_plate=None, good_parts=operation.get("good_parts", 1), parts_per_run=operation.get("parts_per_run", 1), scrap_runs=operation.get("scrap_runs", 0), material_grams_per_run=Decimal(str(operation.get("material_grams_per_run", "0"))), print_hours_per_run=Decimal(str(operation.get("print_hours_per_run", "0"))), provenance={"source": "template", "template_id": template.id, "template_version": template.version}, sort_order=index) for index, operation in enumerate(source_variant.get("operations", []))]
        calculation.variants.append(variant)
    session.add(calculation)
    await session.flush()
    return await _load(session, calculation.id)
