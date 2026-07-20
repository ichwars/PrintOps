from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from math import ceil

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.calculation import Calculation, CalculationRevision
from backend.app.models.commerce import CustomerOrder, Offer, OfferAcceptance
from backend.app.models.commercial_document import (
    CommercialDocument,
    CommercialDocumentLine,
    DocumentRelation,
)
from backend.app.models.number_sequence import NumberSequence
from backend.app.models.project import Project
from backend.app.models.stock_reservation import StockReservation, StockReservationAllocation
from backend.app.services.number_sequence import reserve_number
from backend.app.services.order_errors import ResourceInUseError, ResourceNotFoundError, VersionConflictError
from backend.app.services.small_parts import append_ledger_entry
from backend.app.services.stock_availability import (
    AllocationPlan,
    InsufficientStock,
    allocate_all,
    check_availability,
    requirements_from_snapshot,
)


class InvalidOfferTransition(ResourceInUseError):
    pass


@dataclass(frozen=True)
class AcceptanceResult:
    offer: Offer
    order: CustomerOrder
    project: Project


_OFFER_LOAD = (
    selectinload(Offer.customer),
    selectinload(Offer.business_profile),
    selectinload(Offer.order).selectinload(CustomerOrder.reservations).selectinload(StockReservation.allocations),
)


async def _ensure_sequence(session: AsyncSession, business_profile_id: int, key: str) -> None:
    existing = await session.scalar(
        select(NumberSequence.id).where(
            NumberSequence.business_profile_id == business_profile_id, NumberSequence.key == key
        )
    )
    if existing is not None:
        return
    prefix = "ANG" if key == "offer" else "AUF"
    session.add(
        NumberSequence(
            business_profile_id=business_profile_id,
            key=key,
            prefix=prefix,
            pattern="{PREFIX}-{YYYY}-{#####}",
            next_value=1,
            reset_policy="yearly",
        )
    )
    await session.flush()


async def _load_offer(session: AsyncSession, offer_id: int, *, lock: bool = False) -> Offer:
    statement = select(Offer).where(Offer.id == offer_id).options(*_OFFER_LOAD)
    if lock:
        statement = statement.with_for_update()
    offer = await session.scalar(statement)
    if offer is None:
        raise ResourceNotFoundError(f"Offer {offer_id} was not found")
    return offer


async def list_offers(session: AsyncSession, status: str | None = None) -> list[Offer]:
    statement = select(Offer).options(*_OFFER_LOAD).order_by(Offer.updated_at.desc(), Offer.id.desc())
    if status:
        statement = statement.where(Offer.status == status)
    return list((await session.scalars(statement)).unique())


async def get_offer(session: AsyncSession, offer_id: int) -> Offer:
    return await _load_offer(session, offer_id)


async def create_offer(session: AsyncSession, calculation_revision_id: int) -> Offer:
    revision = await session.get(CalculationRevision, calculation_revision_id)
    if revision is None:
        raise ResourceNotFoundError(f"Calculation revision {calculation_revision_id} was not found")
    calculation = await session.get(Calculation, revision.calculation_id)
    if calculation is None or calculation.status not in {"approved", "superseded"}:
        raise ResourceInUseError("Only an approved calculation revision can become an offer")
    snapshot = deepcopy(revision.snapshot)
    variants = snapshot.get("variants") or []
    preferred_index = next((index for index, item in enumerate(variants) if item.get("is_preferred")), None)
    if preferred_index is None:
        raise ResourceInUseError("Approved snapshot has no preferred variant")
    for index, variant in enumerate(variants):
        variant.setdefault("sort_order", index)
    snapshot["revision"] = {
        "id": revision.id,
        "revision_number": revision.revision_number,
        "production_cost": str(revision.production_cost),
        "selling_price": str(revision.selling_price),
        "currency": revision.currency,
    }
    await _ensure_sequence(session, calculation.business_profile_id, "offer")
    offer = Offer(
        business_profile_id=calculation.business_profile_id,
        customer_id=calculation.customer_id,
        calculation_revision_id=revision.id,
        number=await reserve_number(
            session,
            business_profile_id=calculation.business_profile_id,
            key="offer",
            effective_date=date.today(),
        ),
        preferred_variant_sort_order=int(variants[preferred_index]["sort_order"]),
        snapshot=snapshot,
    )
    session.add(offer)
    await session.flush()
    profile = await session.get(BusinessProfile, offer.business_profile_id)
    if profile is None:
        raise ResourceNotFoundError(f"Business profile {offer.business_profile_id} was not found")
    tax_rate = Decimal(profile.default_tax_rate) if profile.tax_mode == "standard" else Decimal("0.00")
    tax_category_code = "S" if tax_rate else "E"
    net_amount = Decimal(revision.selling_price)
    tax_amount = (net_amount * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
    quotation = CommercialDocument(
        document_type="quotation",
        business_profile_id=offer.business_profile_id,
        customer_id=offer.customer_id,
        source_offer_id=offer.id,
        number=offer.number,
        technical_status="draft",
        language="de-DE",
        currency=revision.currency,
        subtotal_amount=net_amount,
        tax_amount=tax_amount,
        total_amount=net_amount + tax_amount,
        open_amount=net_amount + tax_amount,
        content_options={"legacy_offer_snapshot": True},
    )
    quotation.lines = [
        CommercialDocumentLine(
            position=1,
            description=str((snapshot.get("calculation") or {}).get("title") or offer.number),
            quantity=Decimal("1"),
            unit_code="C62",
            unit_price=net_amount,
            net_amount=net_amount,
            tax_category_code=tax_category_code,
            tax_rate=tax_rate,
            source_data={"calculation_revision_id": revision.id},
            internal_calculation={"production_cost": str(revision.production_cost)},
        )
    ]
    session.add(quotation)
    await session.flush()
    return await _load_offer(session, offer.id)


def _transition(offer: Offer, target: str, expected_version: int) -> None:
    if offer.version != expected_version:
        raise VersionConflictError(f"Offer {offer.id} has changed")
    allowed = {"draft": {"sent"}, "sent": {"accepted", "rejected"}, "accepted": set(), "rejected": set()}
    if target not in allowed.get(offer.status, set()):
        raise InvalidOfferTransition(f"Offer cannot transition from {offer.status} to {target}")
    now = datetime.now(timezone.utc)
    offer.status = target
    offer.version += 1
    setattr(offer, f"{target}_at", now)


async def transition_offer(session: AsyncSession, offer_id: int, target: str, expected_version: int) -> Offer:
    offer = await _load_offer(session, offer_id, lock=True)
    _transition(offer, target, expected_version)
    await session.flush()
    return await _load_offer(session, offer.id)


def _project_targets(snapshot: dict, sort_order: int) -> tuple[int, int]:
    variants = snapshot.get("variants") or []
    variant = next(
        (item for index, item in enumerate(variants) if int(item.get("sort_order", index)) == sort_order), {}
    )
    runs = 0
    parts = 0
    for plate in variant.get("plates") or []:
        good = int(plate.get("good_parts", 0))
        per_print = max(1, int(plate.get("parts_per_print", 1)))
        runs += ceil(good / per_print) + int(plate.get("scrap_prints", 0))
        parts += good
    return runs, parts


async def _persist_reservations(
    session: AsyncSession,
    *,
    order: CustomerOrder,
    project: Project,
    requirements,
    plans: tuple[AllocationPlan, ...],
    actor_id: int | None,
) -> None:
    for requirement in requirements:
        reservation = StockReservation(
            order_id=order.id,
            project_id=project.id,
            source_key=requirement.source_key,
            resource_kind=requirement.resource_kind,
            material_code=requirement.material_code,
            requested_quantity=requirement.quantity,
            unit_code=requirement.unit_code,
        )
        session.add(reservation)
        await session.flush()
        for plan in (item for item in plans if item.source_key == requirement.source_key):
            allocation = StockReservationAllocation(
                reservation_id=reservation.id,
                inventory_backend=plan.candidate.backend,
                spool_id=int(plan.candidate.resource_id) if plan.candidate.backend == "internal" else None,
                external_spool_id=plan.candidate.resource_id if plan.candidate.backend == "spoolman" else None,
                small_part_id=int(plan.candidate.resource_id) if plan.candidate.backend == "small_part" else None,
                allocated_quantity=plan.quantity,
            )
            session.add(allocation)
            await session.flush()
            if allocation.small_part_id is not None:
                await append_ledger_entry(
                    session,
                    small_part_id=allocation.small_part_id,
                    entry_kind="reservation",
                    physical_delta=0,
                    reserved_delta=plan.quantity,
                    reason=f"Reserved for order {order.number}",
                    reference_type="customer_order",
                    reference_id=order.id,
                    actor_id=actor_id,
                    idempotency_key=f"reservation:{allocation.id}",
                )


async def _acceptance_result(session: AsyncSession, acceptance: OfferAcceptance) -> AcceptanceResult:
    offer = await _load_offer(session, acceptance.offer_id)
    order = await session.scalar(
        select(CustomerOrder)
        .where(CustomerOrder.id == acceptance.order_id)
        .options(selectinload(CustomerOrder.reservations).selectinload(StockReservation.allocations))
    )
    project = await session.get(Project, acceptance.project_id)
    if order is None or project is None:
        raise ResourceNotFoundError("Accepted offer result is incomplete")
    return AcceptanceResult(offer, order, project)


async def accept_offer(
    session: AsyncSession,
    *,
    offer_id: int,
    expected_version: int,
    idempotency_key: str,
    actor_id: int | None,
) -> AcceptanceResult:
    replay = await session.scalar(select(OfferAcceptance).where(OfferAcceptance.idempotency_key == idempotency_key))
    if replay is not None:
        if replay.offer_id != offer_id:
            raise ResourceInUseError("Idempotency key belongs to a different offer")
        return await _acceptance_result(session, replay)
    offer = await _load_offer(session, offer_id, lock=True)
    if offer.status != "sent":
        raise InvalidOfferTransition(f"Offer {offer.id} is not sent")
    if offer.version != expected_version:
        raise VersionConflictError(f"Offer {offer.id} has changed")
    requirements = requirements_from_snapshot(offer.snapshot, offer.preferred_variant_sort_order)
    report = await check_availability(session, requirements, lock=True)
    plans = allocate_all(report)
    target_count, target_parts = _project_targets(offer.snapshot, offer.preferred_variant_sort_order)
    calculation_snapshot = offer.snapshot.get("calculation") or {}
    project = Project(
        name=str(calculation_snapshot.get("title") or offer.number),
        status="active",
        target_count=target_count,
        target_parts_count=target_parts,
        notes=f"Created from accepted offer {offer.number}",
    )
    session.add(project)
    await session.flush()
    await _ensure_sequence(session, offer.business_profile_id, "order")
    order = CustomerOrder(
        business_profile_id=offer.business_profile_id,
        customer_id=offer.customer_id,
        offer_id=offer.id,
        project_id=project.id,
        number=await reserve_number(
            session,
            business_profile_id=offer.business_profile_id,
            key="order",
            effective_date=date.today(),
        ),
        accepted_snapshot=offer.snapshot,
    )
    session.add(order)
    await session.flush()
    quotation = await session.scalar(
        select(CommercialDocument)
        .where(CommercialDocument.source_offer_id == offer.id)
        .options(selectinload(CommercialDocument.lines))
    )
    if quotation is None:
        raise ResourceNotFoundError("Accepted offer has no linked quotation document")
    confirmation = CommercialDocument(
        document_type="order_confirmation",
        business_profile_id=order.business_profile_id,
        customer_id=order.customer_id,
        source_order_id=order.id,
        number=order.number,
        technical_status="draft",
        language=quotation.language,
        currency=quotation.currency,
        subtotal_amount=quotation.subtotal_amount,
        tax_amount=quotation.tax_amount,
        total_amount=quotation.total_amount,
        open_amount=quotation.open_amount,
        content_options={"legacy_offer_id": offer.id},
    )
    confirmation.lines = [
        CommercialDocumentLine(
            position=line.position,
            description=line.description,
            quantity=line.quantity,
            unit_code=line.unit_code,
            unit_price=line.unit_price,
            net_amount=line.net_amount,
            tax_category_code=line.tax_category_code,
            tax_rate=line.tax_rate,
            product_identifier=line.product_identifier,
            source_data=dict(line.source_data or {}),
            internal_calculation=dict(line.internal_calculation or {}),
        )
        for line in quotation.lines
    ]
    confirmation.incoming_relations = [
        DocumentRelation(source_document_id=quotation.id, relation_type="successor")
    ]
    session.add(confirmation)
    await session.flush()
    await _persist_reservations(
        session,
        order=order,
        project=project,
        requirements=requirements,
        plans=plans,
        actor_id=actor_id,
    )
    session.add(
        OfferAcceptance(
            offer_id=offer.id,
            idempotency_key=idempotency_key,
            order_id=order.id,
            project_id=project.id,
        )
    )
    _transition(offer, "accepted", expected_version)
    await session.flush()
    acceptance = await session.scalar(select(OfferAcceptance).where(OfferAcceptance.offer_id == offer.id))
    return await _acceptance_result(session, acceptance)


__all__ = [
    "AcceptanceResult",
    "InsufficientStock",
    "accept_offer",
    "create_offer",
    "get_offer",
    "list_offers",
    "transition_offer",
]
