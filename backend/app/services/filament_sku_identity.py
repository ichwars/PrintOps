"""Canonical filament identity: own SKU settings and shared material numbers."""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.filament_sku_settings import FilamentSkuSettings
from backend.app.services import warehouse_number_sequence as numbers


def sku_key(spool: object) -> tuple[str, str, str, str]:
    def value(field: str) -> str:
        raw = spool.get(field) if isinstance(spool, dict) else getattr(spool, field, None)
        return str(raw or "").strip()

    return tuple(value(field) for field in ("material", "subtype", "brand", "color_name"))


async def canonical_sku_settings(db: AsyncSession) -> dict[tuple[str, str, str, str], FilamentSkuSettings]:
    rows = await db.scalars(select(FilamentSkuSettings).order_by(FilamentSkuSettings.id))
    by_key = {}
    for row in rows:
        key = sku_key(row)
        if key not in by_key or (not by_key[key].material_number and row.material_number):
            by_key[key] = row
    return by_key


async def resolve_material_numbers(db: AsyncSession, spools: Iterable[object]) -> dict[int, str | None]:
    """Lookup only, suitable for labels and read routes; never allocate here."""
    by_key = {key: row.material_number for key, row in (await canonical_sku_settings(db)).items()}
    return {int(spool["id"] if isinstance(spool, dict) else spool.id): by_key.get(sku_key(spool)) for spool in spools}


async def enrich_material_numbers(db: AsyncSession, spools: Iterable[object]) -> None:
    items = list(spools)
    mapping = await resolve_material_numbers(db, items)
    for spool in items:
        if isinstance(spool, dict):
            spool["material_number"] = mapping[spool["id"]]
        else:
            spool.material_number = mapping[spool.id]


def sku_predicates(key: tuple[str, str, str, str]) -> tuple:
    """The normalized identity predicate used by every read and writer."""
    return tuple(
        func.trim(func.coalesce(getattr(FilamentSkuSettings, field), "")) == value
        for field, value in zip(("material", "subtype", "brand", "color_name"), key, strict=True)
    )


async def lookup_sku(db: AsyncSession, spool: object) -> FilamentSkuSettings | None:
    """Read the numbered/oldest canonical identity without allocating."""
    return await db.scalar(
        select(FilamentSkuSettings)
        .where(*sku_predicates(sku_key(spool)))
        .order_by(FilamentSkuSettings.material_number.is_(None), FilamentSkuSettings.id)
        .limit(1)
    )


async def sku_alias_ids(db: AsyncSession, sku: object) -> list[int]:
    return list(
        await db.scalars(
            select(FilamentSkuSettings.id).where(*sku_predicates(sku_key(sku))).order_by(FilamentSkuSettings.id)
        )
    )


async def ensure_sku(db: AsyncSession, spool: object, *, material_number: str | None = None) -> FilamentSkuSettings:
    """Serialise group creation and allocation with the existing warehouse writer."""
    key = sku_key(spool)
    if not key[0]:
        raise ValueError("Material is required for a filament SKU")
    await numbers.lock_material_numbers(db)
    row = await lookup_sku(db, spool)
    if row is None:
        fallback = (
            await lookup_sku(db, dict(zip(("material", "subtype", "brand", "color_name"), (*key[:3], ""), strict=True)))
            if key[3]
            else None
        )
        inherited = (
            {
                field: getattr(fallback, field)
                for field in ("lead_time_days", "safety_margin_value", "safety_margin_unit", "alerts_snoozed")
            }
            if fallback is not None
            else {}
        )
        row = FilamentSkuSettings(
            material=key[0], subtype=key[1] or None, brand=key[2] or None, color_name=key[3] or None, **inherited
        )
        db.add(row)
        await db.flush()
    if material_number:
        await numbers.assert_material_number_available(db, material_number, exclude_sku_id=row.id, lock=False)
        row.material_number = material_number
    elif not row.material_number:
        row.material_number = await numbers.reserve_number(db, key="material")
    await db.flush()
    return row


async def backfill_material_numbers(db: AsyncSession) -> None:
    """Add numbered identities while retaining historical SKU IDs and references."""
    from backend.app.models.spool import Spool

    rows = list((await db.scalars(select(FilamentSkuSettings).order_by(FilamentSkuSettings.id))).all())
    rows.extend((await db.scalars(select(Spool).order_by(Spool.id))).all())
    seen = set()
    for row in rows:
        key = sku_key(row)
        if key[0] and key not in seen:
            await ensure_sku(db, row)
            seen.add(key)
