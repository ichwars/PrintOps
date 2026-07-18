from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

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
from backend.app.models.calculation_project import CalculationVariantPlate, CalculationVariantSmallPart
from backend.app.models.customer import Customer
from backend.app.models.equipment import Equipment
from backend.app.models.printer import Printer
from backend.app.models.project import Project
from backend.app.models.settings import Settings
from backend.app.schemas.calculation import CalculationCreate, CalculationUpdate
from backend.app.services.calculation_engine import LaborCostInput, VariantCostInputs, calculate_combined
from backend.app.services.equipment_costs import calculate_hourly_rate
from backend.app.services.order_errors import ResourceInUseError, ResourceNotFoundError, VersionConflictError

_LOAD = (
    selectinload(Calculation.variants).selectinload(CalculationVariant.lines),
    selectinload(Calculation.variants)
    .selectinload(CalculationVariant.operations)
    .selectinload(CalculationOperation.labor),
    selectinload(Calculation.variants)
    .selectinload(CalculationVariant.plates)
    .selectinload(CalculationVariantPlate.project_plate),
    selectinload(Calculation.variants).selectinload(CalculationVariant.small_parts),
    selectinload(Calculation.revisions),
    selectinload(Calculation.business_profile),
    selectinload(Calculation.customer),
    selectinload(Calculation.project),
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


async def _validate_project(session: AsyncSession, project_id: int | None) -> None:
    if project_id is not None and await session.get(Project, project_id) is None:
        raise ResourceNotFoundError(f"Project {project_id} was not found")


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
        "riskPercent": 8,
        "scrapPercent": 8,
        "materialMarkupPercent": 15,
        "discountPercent": 0,
        "taxPercent": 19,
        "minimumPrice": 12,
        "minimumProfit": 4,
        "roundingMode": "none",
        "additionalCosts": 0,
        "explicitPrice": 0,
    }
    try:
        defaults.update(json.loads(stored.get("calculation_defaults", "{}")))
    except (TypeError, ValueError):
        pass
    defaults["materialPricePerKg"] = stored.get("default_filament_cost", "25")
    defaults["electricityPricePerKwh"] = stored.get("energy_cost_per_kwh", "0.15")
    return defaults


async def effective_defaults(session: AsyncSession) -> dict[str, dict[str, str]]:
    defaults = await _cost_defaults(session)
    mapping = {
        "setup_hours": "setupHours",
        "post_processing_hours_per_unit": "postProcessingHours",
        "cad_hours": "cadHours",
        "qa_hours": "qaHours",
        "filament_price_per_kg": "materialPricePerKg",
        "material_markup_percent": "materialMarkupPercent",
        "scrap_percent": "scrapPercent",
        "hourly_rate": "laborRate",
        "consumables": "consumables",
        "packaging": "packaging",
        "shipping": "shipping",
        "discount_percent": "discountPercent",
    }
    return {
        public_key: {"value": str(defaults.get(source_key, 0)), "source": "setting"}
        for public_key, source_key in mapping.items()
    }


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
    variant.plates = [CalculationVariantPlate(**plate.model_dump()) for plate in data.plates]
    variant.small_parts = [CalculationVariantSmallPart(**part.model_dump()) for part in data.small_parts]
    return variant


def _commercial_overrides(values: dict) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}


def _decimal_value(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ResourceInUseError("Calculation provenance contains a non-numeric cost value") from exc


async def create_calculation(session: AsyncSession, data: CalculationCreate) -> Calculation:
    await _validate_references(session, data.business_profile_id, data.customer_id)
    await _validate_project(session, data.project_id)
    values = data.model_dump(exclude={"variants"})
    values["commercial_overrides"] = _commercial_overrides(values["commercial_overrides"])
    calculation = Calculation(**values)
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
    await _validate_project(session, data.project_id)
    for field in (
        "business_profile_id",
        "customer_id",
        "project_id",
        "request_kind",
        "quantity",
        "title",
        "position_description",
        "special_terms",
        "commercial_overrides",
        "currency",
        "notes",
    ):
        value = getattr(data, field)
        if field == "commercial_overrides":
            value = _commercial_overrides(value)
        setattr(calculation, field, value)
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
            "project_id": calculation.project_id,
            "request_kind": calculation.request_kind,
            "quantity": calculation.quantity,
            "position_description": calculation.position_description,
            "special_terms": calculation.special_terms,
            "commercial_overrides": calculation.commercial_overrides,
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
                        "labor": [
                            {
                                "kind": labor.kind,
                                "hours": str(labor.hours),
                                "hourly_rate": str(labor.hourly_rate),
                                "allocation_basis": labor.allocation_basis,
                            }
                            for labor in operation.labor
                        ],
                    }
                    for operation in variant.operations
                ],
                "plates": [
                    {
                        "project_plate_id": item.project_plate_id,
                        "plate_name": item.project_plate.name,
                        "stable_key": item.project_plate.stable_key,
                        "good_parts": item.good_parts,
                        "parts_per_print": item.parts_per_print,
                        "scrap_prints": item.scrap_prints,
                        "material_code": item.material_code,
                        "grams_per_print": str(item.grams_per_print) if item.grams_per_print is not None else None,
                        "hours_per_print": str(item.hours_per_print) if item.hours_per_print is not None else None,
                        "provenance": item.provenance,
                    }
                    for item in variant.plates
                ],
                "small_parts": [
                    {
                        "small_part_id": item.small_part_id,
                        "quantity": str(item.quantity),
                        "description": item.description_snapshot,
                        "unit_code": item.unit_code_snapshot,
                        "unit_cost": str(item.unit_cost_snapshot),
                    }
                    for item in variant.small_parts
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
    if not preferred[0].lines and not preferred[0].plates:
        raise ResourceInUseError("At least one sellable line is required")
    validation = validate_for_approval(calculation)
    if validation["blockers"]:
        raise ResourceInUseError("; ".join(validation["blockers"]))
    missing_reasons = [code for code in validation["warnings"] if not warning_reasons.get(code, "").strip()]
    if missing_reasons:
        raise ResourceInUseError(f"A reason is required for warnings: {', '.join(missing_reasons)}")
    defaults = await _cost_defaults(session)
    overrides = calculation.commercial_overrides or {}
    effective = {**defaults, **overrides}
    default_labor = (
        LaborCostInput(Decimal(str(defaults["setupHours"])), Decimal(str(defaults["laborRate"])), "request"),
        LaborCostInput(Decimal(str(defaults["postProcessingHours"])), Decimal(str(defaults["laborRate"])), "unit"),
        LaborCostInput(Decimal(str(defaults["qaHours"])), Decimal(str(defaults["laborRate"])), "request"),
    )
    operation_inputs: list[VariantCostInputs] = []
    for selected_plate in preferred[0].plates:
        plate = selected_plate.project_plate
        operation_inputs.append(
            VariantCostInputs(
                good_parts=selected_plate.good_parts,
                parts_per_run=selected_plate.parts_per_print,
                scrap_runs=selected_plate.scrap_prints,
                material_grams_per_run=selected_plate.grams_per_print or plate.detected_grams or Decimal("0"),
                material_price_per_kg=Decimal(str(effective.get("material_price_per_kg", defaults["materialPricePerKg"]))),
                material_markup_rate=Decimal(str(effective.get("material_markup_rate", defaults.get("materialMarkupPercent", 0)))) / (Decimal("100") if "material_markup_rate" not in overrides else Decimal("1")),
                print_hours_per_run=selected_plate.hours_per_print or plate.detected_hours or Decimal("0"),
                labor=default_labor,
            )
        )
    for operation in preferred[0].operations if not preferred[0].plates else []:
        labor = (
            tuple(LaborCostInput(item.hours, item.hourly_rate, item.allocation_basis) for item in operation.labor)
            or default_labor
        )
        provenance = operation.provenance or {}
        printer_id = provenance.get("printer_id") if "printer_id" in provenance else defaults.get("defaultPrinterId")
        dryer_id = provenance.get("dryer_id") if "dryer_id" in provenance else defaults.get("defaultDryerId")
        printer = await session.get(Printer, int(printer_id)) if printer_id else None
        dryer = await session.get(Equipment, int(dryer_id)) if dryer_id else None
        printer_rate = printer.hourly_rate if printer is not None else None
        dryer_rate = (
            calculate_hourly_rate(
                dryer.acquisition_value, dryer.service_years, dryer.annual_hours, dryer.maintenance_rate
            )
            if dryer is not None
            else Decimal("0")
        )
        operation_inputs.append(
            VariantCostInputs(
                good_parts=operation.good_parts,
                parts_per_run=operation.parts_per_run,
                scrap_runs=operation.scrap_runs,
                material_grams_per_run=operation.material_grams_per_run,
                material_price_per_kg=Decimal(
                    str(effective.get("material_price_per_kg", defaults["materialPricePerKg"]))
                ),
                material_markup_rate=Decimal(
                    str(effective.get("material_markup_rate", defaults.get("materialMarkupPercent", 0)))
                )
                / (Decimal("100") if "material_markup_rate" not in overrides else Decimal("1")),
                print_hours_per_run=operation.print_hours_per_run,
                machine_cost_per_hour=_decimal_value(provenance.get("printer_hourly_rate") or printer_rate or "0"),
                printer_power_kw=_decimal_value(
                    provenance.get("printer_power_watts") or getattr(printer, "nominal_power_watts", 0) or "0"
                )
                / Decimal("1000"),
                electricity_price_per_kwh=Decimal(str(defaults["electricityPricePerKwh"])),
                drying_hours=_decimal_value(provenance.get("drying_hours") or defaults.get("dryingHours", 0)),
                dryer_power_kw=_decimal_value(
                    provenance.get("dryer_power_watts") or getattr(dryer, "nominal_power_watts", 0) or "0"
                )
                / Decimal("1000"),
                additional_costs=dryer_rate
                * _decimal_value(provenance.get("drying_hours") or defaults.get("dryingHours", 0)),
                labor=labor,
            )
        )
    total_units = max(1, int(sum((line.quantity for line in preferred[0].lines), Decimal("0"))) or sum(item.good_parts for item in preferred[0].plates))
    additive_materials = sum(
        (line.quantity * (line.unit_price or Decimal("0")) for line in preferred[0].lines if line.kind == "material"),
        Decimal("0"),
    )
    additive_materials += sum(
        (item.quantity * item.unit_cost_snapshot for item in preferred[0].small_parts),
        Decimal("0"),
    )
    result = calculate_combined(
        operation_inputs,
        VariantCostInputs(
            good_parts=total_units,
            parts_per_run=1,
            consumables=Decimal(str(effective.get("consumables", defaults.get("consumables", 0)))),
            packaging=Decimal(str(effective.get("packaging", defaults.get("packaging", 0)))),
            additional_costs=Decimal(str(effective.get("additional_costs", defaults.get("additionalCosts", 0)))),
            additive_materials=additive_materials,
            scrap_rate=Decimal(str(effective.get("scrap_rate", defaults.get("scrapPercent", 0))))
            / (Decimal("100") if "scrap_rate" not in overrides else Decimal("1")),
            risk_rate=Decimal(str(effective.get("risk_rate", defaults.get("riskPercent", 0))))
            / (Decimal("100") if "risk_rate" not in overrides else Decimal("1")),
            shipping=Decimal(str(effective.get("shipping", defaults.get("shipping", 0)))),
            price_method=preferred[0].price_method,
            price_rate=Decimal("0") if preferred[0].price_method == "explicit_price" else preferred[0].price_rate,
            explicit_price=preferred[0].price_rate
            if preferred[0].price_method == "explicit_price"
            else Decimal(str(defaults.get("explicitPrice", 0))),
            discount_rate=Decimal(str(effective.get("discount_rate", defaults.get("discountPercent", 0))))
            / (Decimal("100") if "discount_rate" not in overrides else Decimal("1")),
            tax_rate=Decimal(str(effective.get("tax_rate", defaults.get("taxPercent", 0))))
            / (Decimal("100") if "tax_rate" not in overrides else Decimal("1")),
            minimum_price=Decimal(str(effective.get("minimum_price", defaults.get("minimumPrice", 0)))),
            minimum_profit=Decimal(str(effective.get("minimum_profit", defaults.get("minimumProfit", 0)))),
            rounding_mode=str(effective.get("rounding_mode", defaults.get("roundingMode", "none"))),
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


def validate_for_approval(calculation: Calculation) -> dict[str, list[str]]:
    preferred = [variant for variant in calculation.variants if variant.is_preferred]
    blockers: list[str] = []
    warnings: list[str] = []
    if len(preferred) != 1:
        blockers.append("preferred_variant")
        return {"blockers": blockers, "warnings": warnings}
    variant = preferred[0]
    if not variant.lines and not variant.plates:
        blockers.append("sellable_line")
    if not variant.operations and not variant.plates:
        blockers.append("production_operation")
    for operation in variant.operations:
        provenance = operation.provenance or {}
        if provenance.get("source") == "manual":
            warnings.append("manual_source_values")
        try:
            machine_rate = _decimal_value(provenance.get("printer_hourly_rate") or "0")
        except ResourceInUseError:
            blockers.append("invalid_provenance")
            continue
        if machine_rate <= 0 and not provenance.get("printer_id"):
            warnings.append("missing_machine_rate")
        if operation.material_grams_per_run <= 0 or operation.print_hours_per_run <= 0:
            warnings.append("incomplete_production_values")
    for item in variant.plates:
        if (item.grams_per_print or item.project_plate.detected_grams or Decimal("0")) <= 0:
            warnings.append("incomplete_production_values")
        if (item.hours_per_print or item.project_plate.detected_hours or Decimal("0")) <= 0:
            warnings.append("incomplete_production_values")
    return {"blockers": list(dict.fromkeys(blockers)), "warnings": list(dict.fromkeys(warnings))}


async def revise_calculation(session: AsyncSession, calculation_id: int) -> Calculation:
    source = await _load(session, calculation_id, for_update=True)
    if source.status not in {"approved", "superseded"}:
        raise ResourceInUseError("Only approved calculations can be revised")
    revised = Calculation(
        business_profile_id=source.business_profile_id,
        customer_id=source.customer_id,
        project_id=source.project_id,
        request_kind=source.request_kind,
        quantity=source.quantity,
        title=source.title,
        position_description=source.position_description,
        special_terms=source.special_terms,
        commercial_overrides=dict(source.commercial_overrides or {}),
        currency=source.currency,
        notes=source.notes,
    )
    for source_variant in source.variants:
        variant = CalculationVariant(
            name=source_variant.name,
            is_preferred=source_variant.is_preferred,
            sort_order=source_variant.sort_order,
            price_method=source_variant.price_method,
            price_rate=source_variant.price_rate,
        )
        variant.lines = [
            CalculationLine(
                kind=line.kind,
                description=line.description,
                quantity=line.quantity,
                unit_code=line.unit_code,
                unit_price=line.unit_price,
                sort_order=line.sort_order,
            )
            for line in source_variant.lines
        ]
        for source_operation in source_variant.operations:
            operation = CalculationOperation(
                kind=source_operation.kind,
                title=source_operation.title,
                source_file=source_operation.source_file,
                source_plate=source_operation.source_plate,
                good_parts=source_operation.good_parts,
                parts_per_run=source_operation.parts_per_run,
                scrap_runs=source_operation.scrap_runs,
                material_grams_per_run=source_operation.material_grams_per_run,
                print_hours_per_run=source_operation.print_hours_per_run,
                provenance={**(source_operation.provenance or {}), "revised_from": source.id},
                sort_order=source_operation.sort_order,
            )
            operation.labor = [
                CalculationLabor(
                    kind=labor.kind,
                    hours=labor.hours,
                    hourly_rate=labor.hourly_rate,
                    allocation_basis=labor.allocation_basis,
                    sort_order=labor.sort_order,
                )
                for labor in source_operation.labor
            ]
            variant.operations.append(operation)
        variant.plates = [
            CalculationVariantPlate(
                project_plate_id=plate.project_plate_id,
                good_parts=plate.good_parts,
                parts_per_print=plate.parts_per_print,
                scrap_prints=plate.scrap_prints,
                material_code=plate.material_code,
                grams_per_print=plate.grams_per_print,
                hours_per_print=plate.hours_per_print,
                provenance={**(plate.provenance or {}), "revised_from": source.id},
                sort_order=plate.sort_order,
            )
            for plate in source_variant.plates
        ]
        variant.small_parts = [
            CalculationVariantSmallPart(
                small_part_id=part.small_part_id,
                quantity=part.quantity,
                description_snapshot=part.description_snapshot,
                unit_code_snapshot=part.unit_code_snapshot,
                unit_cost_snapshot=part.unit_cost_snapshot,
                sort_order=part.sort_order,
            )
            for part in source_variant.small_parts
        ]
        revised.variants.append(variant)
    source.status = "superseded"
    source.version += 1
    session.add(revised)
    await session.flush()
    return await _load(session, revised.id)


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
    for variant in definition.get("variants", []):
        for operation in variant.get("operations", []):
            operation["provenance"] = {"source": "template"}
    template = CalculationTemplate(
        business_profile_id=calculation.business_profile_id, name=name, definition=definition
    )
    session.add(template)
    await session.flush()
    return template


async def list_templates(session: AsyncSession) -> list[CalculationTemplate]:
    return list(
        (
            await session.scalars(
                select(CalculationTemplate).order_by(CalculationTemplate.name, CalculationTemplate.id)
            )
        ).all()
    )


async def instantiate_template(
    session: AsyncSession, template_id: int, title: str, customer_id: int | None
) -> Calculation:
    template = await session.get(CalculationTemplate, template_id)
    if template is None:
        raise ResourceNotFoundError(f"Calculation template {template_id} was not found")
    definition = template.definition
    calculation_data = definition["calculation"]
    await _validate_references(session, template.business_profile_id, customer_id)
    calculation = Calculation(
        business_profile_id=template.business_profile_id,
        customer_id=customer_id,
        project_id=calculation_data.get("project_id"),
        request_kind=calculation_data.get("request_kind", "single"),
        quantity=calculation_data.get("quantity", 1),
        title=title,
        position_description=calculation_data.get("position_description"),
        special_terms=calculation_data.get("special_terms"),
        commercial_overrides=calculation_data.get("commercial_overrides", {}),
        currency=calculation_data.get("currency", "EUR"),
        notes=None,
    )
    for variant_index, source_variant in enumerate(definition.get("variants", [])):
        variant = CalculationVariant(
            name=source_variant["name"],
            is_preferred=source_variant.get("is_preferred", variant_index == 0),
            sort_order=variant_index,
            price_method=source_variant.get("price_method", "target_margin"),
            price_rate=Decimal(str(source_variant.get("price_rate", "0"))),
        )
        variant.lines = [
            CalculationLine(
                kind=line.get("kind", "printed_part"),
                description=line.get("description", ""),
                quantity=Decimal(str(line.get("quantity", "1"))),
                unit_code=line.get("unit_code", "C62"),
                unit_price=Decimal(str(line["unit_price"])) if line.get("unit_price") is not None else None,
                sort_order=index,
            )
            for index, line in enumerate(source_variant.get("lines", []))
        ]
        variant.operations = []
        for index, operation in enumerate(source_variant.get("operations", [])):
            created_operation = CalculationOperation(
                kind=operation.get("kind", "printing"),
                title=operation.get("title", ""),
                source_file=None,
                source_plate=None,
                good_parts=operation.get("good_parts", 1),
                parts_per_run=operation.get("parts_per_run", 1),
                scrap_runs=operation.get("scrap_runs", 0),
                material_grams_per_run=Decimal(str(operation.get("material_grams_per_run", "0"))),
                print_hours_per_run=Decimal(str(operation.get("print_hours_per_run", "0"))),
                provenance={"source": "template", "template_id": template.id, "template_version": template.version},
                sort_order=index,
            )
            created_operation.labor = [
                CalculationLabor(
                    kind=labor.get("kind", "operator"),
                    hours=Decimal(str(labor.get("hours", "0"))),
                    hourly_rate=Decimal(str(labor.get("hourly_rate", "0"))),
                    allocation_basis=labor.get("allocation_basis", "request"),
                    sort_order=labor_index,
                )
                for labor_index, labor in enumerate(operation.get("labor", []))
            ]
            variant.operations.append(created_operation)
        calculation.variants.append(variant)
    session.add(calculation)
    await session.flush()
    return await _load(session, calculation.id)
