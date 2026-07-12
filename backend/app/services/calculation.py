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
from backend.app.services.calculation_engine import LaborCostInput, VariantCostInputs, calculate_variant
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
    total = Decimal("0")
    for line in preferred[0].lines:
        if line.unit_price is not None:
            total += line.quantity * line.unit_price
    defaults = await _cost_defaults(session)
    service_hours = Decimal(str(defaults["serviceYears"])) * Decimal(str(defaults["annualHours"]))
    machine_hourly = (
        Decimal("0")
        if service_hours <= 0
        else (
            Decimal(str(defaults["acquisitionValue"]))
            / service_hours
            * (Decimal("1") + Decimal(str(defaults["maintenancePercent"])) / Decimal("100"))
        )
    )
    default_labor = (
        LaborCostInput(Decimal(str(defaults["setupHours"])), Decimal(str(defaults["laborRate"])), "request"),
        LaborCostInput(Decimal(str(defaults["postProcessingHours"])), Decimal(str(defaults["laborRate"])), "unit"),
        LaborCostInput(Decimal(str(defaults["qaHours"])), Decimal(str(defaults["laborRate"])), "request"),
    )
    production = Decimal("0")
    for operation in preferred[0].operations:
        labor = (
            tuple(LaborCostInput(item.hours, item.hourly_rate, item.allocation_basis) for item in operation.labor)
            or default_labor
        )
        production += calculate_variant(
            VariantCostInputs(
                good_parts=operation.good_parts,
                parts_per_run=operation.parts_per_run,
                scrap_runs=operation.scrap_runs,
                material_grams_per_run=operation.material_grams_per_run,
                material_price_per_kg=Decimal(str(defaults["materialPricePerKg"])),
                print_hours_per_run=operation.print_hours_per_run,
                machine_cost_per_hour=machine_hourly,
                printer_power_kw=Decimal("0.2"),
                electricity_price_per_kwh=Decimal(str(defaults["electricityPricePerKwh"])),
                labor=labor,
                consumables=Decimal(str(defaults["consumables"])),
                packaging=Decimal(str(defaults["packaging"])),
            )
        ).production_cost
    revision_number = 1 + max((revision.revision_number for revision in calculation.revisions), default=0)
    snapshot = _snapshot(calculation, warning_reasons)
    snapshot["cost_defaults"] = {key: str(value) for key, value in defaults.items()}
    revision = CalculationRevision(
        calculation_id=calculation.id,
        revision_number=revision_number,
        snapshot=snapshot,
        production_cost=production,
        selling_price=total,
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
