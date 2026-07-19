from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.filament_sku_settings import FilamentSkuSettings
from backend.app.models.procurement import ProcurementOffer, Supplier
from backend.app.models.small_part import SmallPart
from backend.app.schemas.procurement import (
    FilamentResource,
    MaterialResource,
    ProcurementOfferWrite,
    SupplierCreate,
    SupplierUpdate,
    supplier_name_key,
)
from backend.app.services.order_errors import ResourceInUseError


@dataclass(frozen=True, slots=True)
class SupplierPage:
    items: list[Supplier]
    total: int
    limit: int
    offset: int


class ProcurementResourceNotFound(LookupError):
    pass


class InvalidProcurementReplacement(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedResource:
    resource_key: str
    small_part_id: int | None
    filament_sku_settings_id: int | None
    small_part: SmallPart | None = None


@dataclass(frozen=True, slots=True)
class ProcurementOfferResult:
    offer: ProcurementOffer
    supplier: Supplier


async def list_suppliers(
    session: AsyncSession,
    *,
    q: str | None = None,
    active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> SupplierPage:
    filters = []
    if active is not None:
        filters.append(Supplier.is_active == active)
    if q is not None and (normalized_query := q.strip().casefold()):
        filters.append(
            or_(
                Supplier.name_key.contains(normalized_query, autoescape=True),
                func.lower(Supplier.contact_name).contains(normalized_query, autoescape=True),
                func.lower(Supplier.email).contains(normalized_query, autoescape=True),
                func.lower(Supplier.customer_number).contains(normalized_query, autoescape=True),
            )
        )

    total = await session.scalar(select(func.count(Supplier.id)).where(*filters))
    items = list(
        await session.scalars(
            select(Supplier)
            .where(*filters)
            .order_by(Supplier.name_key, Supplier.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return SupplierPage(items=items, total=total or 0, limit=limit, offset=offset)


async def get_supplier(session: AsyncSession, supplier_id: int) -> Supplier | None:
    return await session.get(Supplier, supplier_id)


async def create_supplier(session: AsyncSession, data: SupplierCreate) -> Supplier:
    supplier = Supplier(**data.model_dump(), name_key=supplier_name_key(data.name))
    session.add(supplier)
    await session.flush()
    return supplier


async def update_supplier(session: AsyncSession, supplier_id: int, data: SupplierUpdate) -> Supplier | None:
    supplier = await get_supplier(session, supplier_id)
    if supplier is None:
        return None

    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        supplier.name_key = supplier_name_key(changes["name"])
    for field, value in changes.items():
        setattr(supplier, field, value)
    await session.flush()
    return supplier


async def delete_supplier(session: AsyncSession, supplier_id: int) -> bool:
    supplier = await get_supplier(session, supplier_id)
    if supplier is None:
        return False
    if await session.scalar(select(func.count(ProcurementOffer.id)).where(ProcurementOffer.supplier_id == supplier_id)):
        raise ResourceInUseError("Supplier is referenced by procurement offers")
    await session.delete(supplier)
    return True


async def resolve_resource(
    session: AsyncSession,
    resource: MaterialResource | FilamentResource,
    *,
    create_filament: bool,
) -> ResolvedResource | None:
    if isinstance(resource, MaterialResource):
        small_part = await session.get(SmallPart, resource.small_part_id)
        if small_part is None:
            raise ProcurementResourceNotFound(f"Material {resource.small_part_id} was not found")
        return ResolvedResource(
            resource_key=f"material:{small_part.id}",
            small_part_id=small_part.id,
            filament_sku_settings_id=None,
            small_part=small_part,
        )

    statement = select(FilamentSkuSettings).where(
        FilamentSkuSettings.material == resource.material,
        FilamentSkuSettings.subtype == resource.subtype,
        FilamentSkuSettings.brand == resource.brand,
        FilamentSkuSettings.color_name == resource.color_name,
    )
    settings = await session.scalar(statement)
    if settings is None:
        if not create_filament:
            return None
        settings = FilamentSkuSettings(
            material=resource.material,
            subtype=resource.subtype,
            brand=resource.brand,
            color_name=resource.color_name,
        )
        session.add(settings)
        await session.flush()
    return ResolvedResource(
        resource_key=f"filament:{settings.id}",
        small_part_id=None,
        filament_sku_settings_id=settings.id,
    )


async def list_offers(
    session: AsyncSession,
    resource: MaterialResource | FilamentResource,
    *,
    active: bool,
) -> list[ProcurementOfferResult]:
    resolved = await resolve_resource(session, resource, create_filament=False)
    if resolved is None:
        return []
    return await _offers_for_resource(session, resolved.resource_key, active=active)


async def _offers_for_resource(
    session: AsyncSession,
    resource_key: str,
    *,
    active: bool,
) -> list[ProcurementOfferResult]:
    rows = (
        await session.execute(
            select(ProcurementOffer, Supplier)
            .join(Supplier, Supplier.id == ProcurementOffer.supplier_id)
            .where(
                ProcurementOffer.resource_key == resource_key,
                ProcurementOffer.is_active == active,
            )
            .order_by(ProcurementOffer.is_preferred.desc(), Supplier.name_key, ProcurementOffer.id)
        )
    ).all()
    return [ProcurementOfferResult(offer=offer, supplier=supplier) for offer, supplier in rows]


async def preferred_offers_for_materials(
    session: AsyncSession,
    material_ids: list[int],
) -> dict[int, ProcurementOfferResult]:
    if not material_ids:
        return {}
    rows = (
        await session.execute(
            select(ProcurementOffer, Supplier)
            .join(Supplier, Supplier.id == ProcurementOffer.supplier_id)
            .where(
                ProcurementOffer.small_part_id.in_(set(material_ids)),
                ProcurementOffer.is_active.is_(True),
                ProcurementOffer.is_preferred.is_(True),
            )
        )
    ).all()
    return {
        offer.small_part_id: ProcurementOfferResult(offer=offer, supplier=supplier)
        for offer, supplier in rows
        if offer.small_part_id is not None
    }


async def replace_offers(
    session: AsyncSession,
    resource: MaterialResource | FilamentResource,
    drafts: list[ProcurementOfferWrite],
) -> list[ProcurementOfferResult]:
    if sum(draft.is_active and draft.is_preferred for draft in drafts) > 1:
        raise InvalidProcurementReplacement("Only one active preferred offer is allowed")

    submitted_ids = [draft.id for draft in drafts if draft.id is not None]
    if len(submitted_ids) != len(set(submitted_ids)):
        raise InvalidProcurementReplacement("An offer ID may only be submitted once")

    resolved = await resolve_resource(session, resource, create_filament=False)
    existing = (
        list(
            await session.scalars(
                select(ProcurementOffer).where(ProcurementOffer.resource_key == resolved.resource_key)
            )
        )
        if resolved is not None
        else []
    )
    existing_by_id = {offer.id: offer for offer in existing}
    for offer_id in submitted_ids:
        if offer_id not in existing_by_id:
            resource_key = resolved.resource_key if resolved is not None else "the missing resource"
            raise InvalidProcurementReplacement(
                f"Offer {offer_id} does not belong to {resource_key}"
            )

    supplier_ids = {draft.supplier_id for draft in drafts}
    suppliers = {
        supplier.id: supplier
        for supplier in await session.scalars(select(Supplier).where(Supplier.id.in_(supplier_ids)))
    }
    missing_supplier_ids = supplier_ids - suppliers.keys()
    if missing_supplier_ids:
        missing = min(missing_supplier_ids)
        raise InvalidProcurementReplacement(f"Supplier {missing} was not found")
    inactive_supplier_ids = {supplier_id for supplier_id, supplier in suppliers.items() if not supplier.is_active}
    if inactive_supplier_ids:
        inactive = min(inactive_supplier_ids)
        raise InvalidProcurementReplacement(f"Supplier {inactive} is inactive")

    if resolved is None:
        resolved = await resolve_resource(session, resource, create_filament=True)
        assert resolved is not None

    for offer in existing:
        if offer.is_preferred:
            offer.is_preferred = False
    await session.flush()

    included_ids: set[int] = set()
    for draft in drafts:
        values = draft.model_dump(exclude={"id"})
        values["lead_time_days"] = (
            draft.lead_time_days
            if draft.lead_time_days is not None
            else suppliers[draft.supplier_id].default_lead_time_days
        )
        if draft.id is None:
            offer = ProcurementOffer(
                **values,
                resource_key=resolved.resource_key,
                small_part_id=resolved.small_part_id,
                filament_sku_settings_id=resolved.filament_sku_settings_id,
            )
            session.add(offer)
        else:
            offer = existing_by_id[draft.id]
            included_ids.add(offer.id)
            for field, value in values.items():
                setattr(offer, field, value)

    for offer in existing:
        if offer.id not in included_ids:
            offer.is_active = False
            offer.is_preferred = False

    preferred = next((draft for draft in drafts if draft.is_active and draft.is_preferred), None)
    if preferred is not None and resolved.small_part is not None:
        resolved.small_part.unit_cost = preferred.net_price

    await session.flush()
    return await _offers_for_resource(session, resolved.resource_key, active=True)


async def deactivate_offer(session: AsyncSession, offer_id: int) -> bool:
    offer = await session.get(ProcurementOffer, offer_id)
    if offer is None:
        return False
    offer.is_active = False
    offer.is_preferred = False
    await session.flush()
    return True
