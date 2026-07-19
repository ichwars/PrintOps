from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.procurement import ProcurementOffer, Supplier
from backend.app.schemas.procurement import SupplierCreate, SupplierUpdate, supplier_name_key
from backend.app.services.order_errors import ResourceInUseError


@dataclass(frozen=True, slots=True)
class SupplierPage:
    items: list[Supplier]
    total: int
    limit: int
    offset: int


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
