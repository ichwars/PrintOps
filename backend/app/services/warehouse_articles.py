"""Article master data. Callers own the transaction and commit."""

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.calculation import CalculationRevision
from backend.app.models.location import Location
from backend.app.models.project import Project
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.warehouse_article import WarehouseArticle, WarehouseArticleLedgerEntry
from backend.app.schemas.warehouse_article import (
    WarehouseArticleCreate,
    WarehouseArticleRead,
    WarehouseArticleUpdate,
    WarehouseBalance,
    WarehouseLocationBalance,
)
from backend.app.services.small_parts import get_balance as material_balance

ZERO = Decimal("0")
MAX_QUANTITY = Decimal("999999999999.999999")


class WarehouseError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code = code
        self.status = status
        super().__init__(message)


async def load_article(session: AsyncSession, article_id: int, *, lock: bool = False) -> WarehouseArticle:
    if lock:
        # A write before the first stock read serializes SQLite writers and locks
        # the article row on PostgreSQL. A process-local asyncio lock is not enough.
        await session.execute(
            update(WarehouseArticle)
            .where(WarehouseArticle.id == article_id)
            .values(version=WarehouseArticle.version, updated_at=WarehouseArticle.updated_at)
            .execution_options(synchronize_session=False)
        )
    article = await session.scalar(
        select(WarehouseArticle).where(WarehouseArticle.id == article_id).execution_options(populate_existing=True)
    )
    if article is None:
        raise WarehouseError("not_found", "Artikel nicht gefunden", 404)
    return article


async def has_history(session: AsyncSession, article: WarehouseArticle) -> bool:
    own = await session.scalar(
        select(WarehouseArticleLedgerEntry.id).where(WarehouseArticleLedgerEntry.article_id == article.id).limit(1)
    )
    if own:
        return True
    if article.small_part_id:
        return bool(
            await session.scalar(
                select(SmallPartLedgerEntry.id)
                .where(SmallPartLedgerEntry.small_part_id == article.small_part_id)
                .limit(1)
            )
        )
    return False


def check_precision(quantity: Decimal, unit: SmallPartUnit):
    if quantity != quantity.quantize(Decimal(1).scaleb(-unit.decimal_places)):
        raise WarehouseError(
            "unit_precision", f"Einheit {unit.code} erlaubt {unit.decimal_places} Nachkommastellen", 422
        )


async def validate_article(session: AsyncSession, data: WarehouseArticleCreate, article_id: int | None = None):
    # Serialize catalog deletion/precision changes with new article references.
    await session.execute(
        update(SmallPartUnit).where(SmallPartUnit.code == data.unit_code).values(code=SmallPartUnit.code)
    )
    unit = await session.get(SmallPartUnit, data.unit_code)
    if unit is None or not unit.is_active:
        raise WarehouseError("invalid_unit", "Eine aktive lokale Einheit muss bestätigt werden", 422)
    check_precision(data.minimum_stock, unit)
    if data.kind == "service":
        if data.stock_source != "none" or data.small_part_id is not None or data.minimum_stock != 0:
            raise WarehouseError("invalid_stock_source", "Dienstleistungen führen keinen Bestand", 422)
    elif data.stock_source == "none":
        raise WarehouseError("invalid_stock_source", "Produkte benötigen eine Bestandsquelle", 422)
    if (data.stock_source == "material") != (data.small_part_id is not None):
        raise WarehouseError("invalid_stock_source", "Materialbestand benötigt genau einen Materialdatensatz", 422)
    if data.small_part_id is not None:
        await session.execute(
            update(SmallPart)
            .where(SmallPart.id == data.small_part_id)
            .values(id=SmallPart.id, updated_at=SmallPart.updated_at)
        )
        material = await session.get(SmallPart, data.small_part_id)
        if material is None or not material.is_active or material.unit_code != data.unit_code:
            raise WarehouseError("invalid_material", "Aktives Material mit derselben Einheit erforderlich", 422)
        owner = await session.scalar(
            select(WarehouseArticle.id).where(WarehouseArticle.small_part_id == data.small_part_id)
        )
        if owner is not None and owner != article_id:
            raise WarehouseError("material_claimed", "Material ist bereits einem Verkaufsartikel zugeordnet")
        if not data.is_active:
            balance = await material_balance(session, material.id)
            if balance.physical != 0 or balance.reserved != 0:
                raise WarehouseError(
                    "stock_remaining", "Artikel mit Materialbestand kann nicht archiviert angelegt werden"
                )
    if (data.project_id is not None or data.calculation_revision_id is not None) and data.kind != "finished":
        raise WarehouseError(
            "invalid_production_reference", "Produktionsbezug ist nur bei Fertigprodukten möglich", 422
        )
    for model, identifier in ((Project, data.project_id), (CalculationRevision, data.calculation_revision_id)):
        if model is Project and identifier is not None:
            await session.execute(update(Project).where(Project.id == identifier).values(id=Project.id))
        if identifier is not None and await session.get(model, identifier) is None:
            raise WarehouseError("invalid_reference", "Produktionsbezug nicht gefunden", 422)


async def create_article(session: AsyncSession, data: WarehouseArticleCreate) -> WarehouseArticle:
    await validate_article(session, data)
    article = WarehouseArticle(**data.model_dump())
    session.add(article)
    await session.flush()
    return article


async def update_article(session: AsyncSession, article_id: int, data: WarehouseArticleUpdate) -> WarehouseArticle:
    article = await load_article(session, article_id, lock=True)
    if article.small_part_id is not None:
        await session.execute(
            update(SmallPart)
            .where(SmallPart.id == article.small_part_id)
            .values(id=SmallPart.id, updated_at=SmallPart.updated_at)
        )
    if data.version != article.version:
        raise WarehouseError("stale_version", "Artikel wurde geändert. Bitte neu laden")
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    protected = {"unit_code", "stock_source", "small_part_id", "kind"}
    if any(key in changes and changes[key] != getattr(article, key) for key in protected) and await has_history(
        session, article
    ):
        raise WarehouseError(
            "stock_identity_frozen", "Einheit, Artikelart und Bestandsquelle sind nach der ersten Buchung gesperrt"
        )
    combined = {key: getattr(article, key) for key in WarehouseArticleCreate.model_fields}
    combined.update(changes)
    await validate_article(session, WarehouseArticleCreate.model_validate(combined), article.id)
    if not combined["is_active"]:
        balances = await location_balances(session, article)
        if any(row.physical != 0 or row.reserved != 0 for row in balances):
            raise WarehouseError(
                "stock_remaining", "Artikel mit Bestand oder Reservierungen kann nicht archiviert werden"
            )
    for key, value in changes.items():
        setattr(article, key, value)
    article.version += 1
    await session.flush()
    return article


async def location_balances(session: AsyncSession, article: WarehouseArticle) -> list[WarehouseLocationBalance]:
    if article.stock_source == "none":
        return []
    if article.stock_source == "material":
        material = await session.get(SmallPart, article.small_part_id)
        if material is None:
            raise WarehouseError("invalid_material", "Verknüpftes Material fehlt")
        balance = await material_balance(session, material.id)
        location = await session.get(Location, material.location_id) if material.location_id else None
        return [
            WarehouseLocationBalance(
                location_id=material.location_id,
                location_name=location.name if location else "Ohne Lagerort",
                physical=balance.physical,
                reserved=balance.reserved,
                available=balance.available,
            )
        ]
    entries = list(
        await session.scalars(
            select(WarehouseArticleLedgerEntry).where(WarehouseArticleLedgerEntry.article_id == article.id)
        )
    )
    totals: dict[int, list[Decimal]] = {}
    for entry in entries:
        value = totals.setdefault(entry.location_id, [ZERO, ZERO])
        value[0] += entry.physical_delta
        value[1] += entry.reserved_delta
        if entry.target_location_id is not None:
            totals.setdefault(entry.target_location_id, [ZERO, ZERO])[0] -= entry.physical_delta
    names = (
        dict((await session.execute(select(Location.id, Location.name).where(Location.id.in_(totals)))).all())
        if totals
        else {}
    )
    return [
        WarehouseLocationBalance(
            location_id=key,
            location_name=names.get(key, f"#{key}"),
            physical=value[0],
            reserved=value[1],
            available=value[0] - value[1],
        )
        for key, value in sorted(totals.items())
    ]


async def read_article(session: AsyncSession, article: WarehouseArticle) -> WarehouseArticleRead:
    locations = await location_balances(session, article)
    physical = sum((row.physical for row in locations), ZERO)
    reserved = sum((row.reserved for row in locations), ZERO)
    return WarehouseArticleRead(
        **{key: getattr(article, key) for key in WarehouseArticleCreate.model_fields},
        id=article.id,
        version=article.version,
        created_at=article.created_at,
        updated_at=article.updated_at,
        has_history=await has_history(session, article),
        locations=locations,
        balance=WarehouseBalance(
            physical=physical,
            reserved=reserved,
            available=physical - reserved,
            is_low_stock=article.stock_source != "none" and physical - reserved < article.minimum_stock,
        ),
    )
