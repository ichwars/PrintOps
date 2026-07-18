from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.small_part import SmallPart
from backend.app.models.spool import Spool
from backend.app.models.stock_reservation import StockReservation, StockReservationAllocation
from backend.app.services.small_parts import get_balance


@dataclass(frozen=True)
class StockRequirement:
    source_key: str
    resource_kind: Literal["filament", "small_part"]
    quantity: Decimal
    unit_code: str
    material_code: str | None = None
    small_part_id: int | None = None
    description: str | None = None


@dataclass(frozen=True)
class StockCandidate:
    backend: Literal["internal", "spoolman", "small_part"]
    resource_id: str
    available: Decimal
    material_code: str | None = None


@dataclass(frozen=True)
class AllocationPlan:
    source_key: str
    candidate: StockCandidate
    quantity: Decimal


@dataclass(frozen=True)
class AvailabilityLine:
    requirement: StockRequirement
    status: Literal["available", "short", "unmapped"]
    physical: Decimal
    reserved: Decimal
    available: Decimal
    shortage: Decimal
    allocations: tuple[AllocationPlan, ...]


@dataclass(frozen=True)
class AvailabilityReport:
    lines: tuple[AvailabilityLine, ...]
    checked_at: datetime


class InsufficientStock(ValueError):
    def __init__(self, shortage: Decimal, lines: tuple[AvailabilityLine, ...] = ()):
        self.shortage = shortage
        self.lines = lines
        super().__init__(f"Insufficient stock ({shortage} missing)")


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _material(value: str | None) -> str:
    normalized = (value or "").strip().casefold().replace("_", " ").replace("-", " ")
    for code in ("petg", "pla", "abs", "asa", "tpu", "pc", "pa", "hips", "pva", "pp", "pet"):
        if code in normalized.split() or normalized.startswith(code):
            return code
    return normalized.replace(" ", "")


def allocate_candidates(
    source_key: str, quantity: Decimal, candidates: list[StockCandidate]
) -> tuple[AllocationPlan, ...]:
    remaining = Decimal(quantity)
    plans: list[AllocationPlan] = []
    for candidate in sorted(candidates, key=lambda item: (item.backend, int(item.resource_id) if item.resource_id.isdigit() else item.resource_id)):
        if remaining <= 0:
            break
        allocated = min(remaining, candidate.available)
        if allocated > 0:
            plans.append(AllocationPlan(source_key, candidate, allocated))
            remaining -= allocated
    if remaining > 0:
        raise InsufficientStock(remaining)
    return tuple(plans)


def requirements_from_snapshot(snapshot: dict, variant_sort_order: int) -> tuple[StockRequirement, ...]:
    variants = snapshot.get("variants") or []
    variant = next(
        (item for item in variants if int(item.get("sort_order", variants.index(item))) == variant_sort_order),
        None,
    )
    if variant is None:
        raise ValueError("Selected offer variant is missing from the approved snapshot")
    requirements: list[StockRequirement] = []
    for index, plate in enumerate(variant.get("plates") or []):
        grams = _decimal(plate.get("grams_per_print"))
        material_code = str(plate.get("material_code") or "").strip() or None
        runs = ceil(int(plate.get("good_parts", 0)) / max(1, int(plate.get("parts_per_print", 1))))
        runs += int(plate.get("scrap_prints", 0))
        quantity = grams * runs
        if quantity <= 0 or not material_code:
            raise ValueError("A selected plate has no reservable material requirement")
        requirements.append(
            StockRequirement(
                source_key=f"plate:{plate.get('stable_key') or plate.get('project_plate_id') or index}",
                resource_kind="filament",
                quantity=quantity,
                unit_code="GRM",
                material_code=material_code,
                description=str(plate.get("plate_name") or plate.get("stable_key") or f"Plate {index + 1}"),
            )
        )
    for index, part in enumerate(variant.get("small_parts") or []):
        part_id = int(part.get("small_part_id", 0))
        quantity = _decimal(part.get("quantity"))
        if part_id <= 0 or quantity <= 0:
            raise ValueError("A small-part requirement is incomplete")
        requirements.append(
            StockRequirement(
                source_key=f"small-part:{part_id}:{index}",
                resource_kind="small_part",
                quantity=quantity,
                unit_code=str(part.get("unit_code") or part.get("unit_code_snapshot") or "C62"),
                small_part_id=part_id,
                description=str(part.get("description") or part.get("description_snapshot") or f"Small part {part_id}"),
            )
        )
    return tuple(requirements)


async def _filament_reserved(session: AsyncSession, spool_id: int) -> Decimal:
    value = await session.scalar(
        select(func.coalesce(func.sum(StockReservationAllocation.allocated_quantity - StockReservationAllocation.consumed_quantity), 0))
        .join(StockReservation, StockReservation.id == StockReservationAllocation.reservation_id)
        .where(StockReservationAllocation.spool_id == spool_id, StockReservation.status == "active")
    )
    return Decimal(value or 0)


async def check_availability(
    session: AsyncSession, requirements: tuple[StockRequirement, ...], *, lock: bool = False
) -> AvailabilityReport:
    statement = select(Spool).where(Spool.archived_at.is_(None)).order_by(Spool.created_at, Spool.id)
    if lock:
        statement = statement.with_for_update()
    spools = list(await session.scalars(statement))
    lines: list[AvailabilityLine] = []
    for requirement in requirements:
        if requirement.resource_kind == "small_part":
            part_statement = select(SmallPart).where(SmallPart.id == requirement.small_part_id)
            if lock:
                part_statement = part_statement.with_for_update()
            part = await session.scalar(part_statement)
            if part is None or not part.is_active:
                lines.append(AvailabilityLine(requirement, "unmapped", Decimal("0"), Decimal("0"), Decimal("0"), requirement.quantity, ()))
                continue
            balance = await get_balance(session, part.id)
            candidate = StockCandidate("small_part", str(part.id), balance.available)
            try:
                plans = allocate_candidates(requirement.source_key, requirement.quantity, [candidate])
                status: Literal["available", "short", "unmapped"] = "available"
                shortage = Decimal("0")
            except InsufficientStock as error:
                plans, status, shortage = (), "short", error.shortage
            lines.append(
                AvailabilityLine(
                    requirement, status, balance.physical, balance.reserved, balance.available, shortage, plans
                )
            )
            continue
        candidates: list[StockCandidate] = []
        physical = Decimal("0")
        reserved = Decimal("0")
        for spool in spools:
            if _material(spool.material) != _material(requirement.material_code):
                continue
            spool_physical = max(Decimal("0"), _decimal(spool.label_weight) - _decimal(spool.weight_used))
            spool_reserved = await _filament_reserved(session, spool.id)
            available = max(Decimal("0"), spool_physical - spool_reserved)
            physical += spool_physical
            reserved += spool_reserved
            candidates.append(StockCandidate("internal", str(spool.id), available, spool.material))
        available = sum((candidate.available for candidate in candidates), Decimal("0"))
        if not candidates:
            lines.append(AvailabilityLine(requirement, "unmapped", physical, reserved, available, requirement.quantity, ()))
            continue
        try:
            plans = allocate_candidates(requirement.source_key, requirement.quantity, candidates)
            status = "available"
            shortage = Decimal("0")
        except InsufficientStock as error:
            plans, status, shortage = (), "short", error.shortage
        lines.append(AvailabilityLine(requirement, status, physical, reserved, available, shortage, plans))
    return AvailabilityReport(tuple(lines), datetime.now(timezone.utc))


def allocate_all(report: AvailabilityReport) -> tuple[AllocationPlan, ...]:
    short = tuple(line for line in report.lines if line.status != "available")
    if short:
        raise InsufficientStock(sum((line.shortage for line in short), Decimal("0")), short)
    return tuple(plan for line in report.lines for plan in line.allocations)
