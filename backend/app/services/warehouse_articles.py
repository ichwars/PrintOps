"""Article master data. Callers own the transaction and commit."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from sqlite3 import OperationalError as SQLiteOperationalError

from sqlalchemy import Select, String, case, func, select, type_coerce, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import TypeDecorator

from backend.app.models.calculation import CalculationRevision
from backend.app.models.location import Location
from backend.app.models.project import Project
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.warehouse_article import WarehouseArticle, WarehouseArticleLedgerEntry, WarehouseDecimal
from backend.app.schemas.warehouse_article import (
    WarehouseArticleCreate,
    WarehouseArticleRead,
    WarehouseArticleUpdate,
    WarehouseBalance,
    WarehouseForecastPage,
    WarehouseForecastRow,
    WarehouseLocationBalance,
)
from backend.app.services import warehouse_number_sequence as numbers
from backend.app.services.inventory_stocktake import stock_timestamp_parameter
from backend.app.services.small_parts import StockUsage, get_balance as material_balance, usage_for_parts

ZERO = Decimal("0")
MAX_QUANTITY = Decimal("999999999999.999999")
FORECAST_WINDOW_DAYS = 30


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
    try:
        await numbers.assert_material_number_available(
            session, data.sku, exclude_article_id=article_id, exclude_small_part_id=data.small_part_id, lock=False
        )
    except ValueError as exc:
        raise WarehouseError("material_number_conflict", str(exc)) from exc
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
    await numbers.lock_material_numbers(session)
    await validate_article(session, data)
    article = WarehouseArticle(**data.model_dump())
    session.add(article)
    await session.flush()
    return article


async def update_article(session: AsyncSession, article_id: int, data: WarehouseArticleUpdate) -> WarehouseArticle:
    # Always take the shared namespace writer before article/material row locks.
    await numbers.lock_material_numbers(session)
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


def _article_balance(source: str, minimum_stock: Decimal, physical: Decimal, reserved: Decimal) -> WarehouseBalance:
    available = physical - reserved
    return WarehouseBalance(
        physical=physical,
        reserved=reserved,
        available=available,
        is_low_stock=source != "none" and available < minimum_stock,
    )


class _SQLiteScaledSum(TypeDecorator):
    """Decode the overflow path's integer millionths without SQLite arithmetic."""

    impl = String
    cache_ok = True

    def process_result_value(self, value, dialect):
        return Decimal(sum(map(int, value.split(",")))) / 1_000_000 if value is not None else None


def _scaled_sum(value, sqlite_wide: bool):
    if sqlite_wide:
        return type_coerce(func.group_concat(value), _SQLiteScaledSum())
    return type_coerce(func.sum(value), WarehouseDecimal())


async def _execute_stock_sums(session: AsyncSession, query: Callable[[bool], Select]):
    try:
        return await session.execute(query(False))
    except OperationalError as exc:
        if not isinstance(exc.orig, SQLiteOperationalError) or str(exc.orig) != "integer overflow":
            raise
    # SQLite SUM(int) can overflow even with individually valid ledger entries.
    # The failed SELECT leaves the transaction usable. Retry as one SELECT to
    # keep stock balances and consumption in the same snapshot.
    return await session.execute(query(True))


def _article_stock_query(statement: Select[tuple[WarehouseArticle]], sqlite_wide: bool):
    candidates = statement.with_only_columns(
        WarehouseArticle.id,
        WarehouseArticle.name,
        WarehouseArticle.sku,
        WarehouseArticle.unit_code,
        WarehouseArticle.stock_source,
        WarehouseArticle.small_part_id,
        WarehouseArticle.minimum_stock,
    ).cte("candidates")
    own_entry = WarehouseArticleLedgerEntry
    # A transfer moves physical stock between locations without changing the article total.
    own = (
        select(
            own_entry.article_id,
            _scaled_sum(
                case((own_entry.target_location_id.is_(None), own_entry.physical_delta), else_=0), sqlite_wide
            ).label("physical"),
            _scaled_sum(own_entry.reserved_delta, sqlite_wide).label("reserved"),
        )
        .join(candidates, candidates.c.id == own_entry.article_id)
        .group_by(own_entry.article_id)
        .subquery()
    )
    material_entry = SmallPartLedgerEntry
    material = (
        select(
            material_entry.small_part_id,
            func.sum(material_entry.physical_delta).label("physical"),
            func.sum(material_entry.reserved_delta).label("reserved"),
        )
        .join(candidates, candidates.c.small_part_id == material_entry.small_part_id)
        .group_by(material_entry.small_part_id)
        .subquery()
    )
    return candidates, (
        select(
            candidates.c.id,
            candidates.c.stock_source,
            candidates.c.minimum_stock,
            own.c.physical.label("own_physical"),
            own.c.reserved.label("own_reserved"),
            material.c.physical.label("material_physical"),
            material.c.reserved.label("material_reserved"),
        )
        .outerjoin(own, candidates.c.id == own.c.article_id)
        .outerjoin(material, candidates.c.small_part_id == material.c.small_part_id)
    )


async def balances_for_listing(
    session: AsyncSession, statement: Select[tuple[WarehouseArticle]]
) -> list[tuple[int, WarehouseBalance | None]]:
    """Read exact article totals in one query, without loading the individual journals."""

    def query(sqlite_wide: bool):
        candidates, stock = _article_stock_query(statement, sqlite_wide)
        return stock.order_by(candidates.c.name, candidates.c.id)

    rows = await _execute_stock_sums(session, query)
    return [
        (
            article_id,
            None
            if source == "none"
            else _article_balance(
                source,
                minimum,
                (material_physical if source == "material" else own_physical) or ZERO,
                (material_reserved if source == "material" else own_reserved) or ZERO,
            ),
        )
        for article_id, source, minimum, own_physical, own_reserved, material_physical, material_reserved in rows
    ]


def active_article_issue():
    entry = WarehouseArticleLedgerEntry
    counter = aliased(entry)
    return entry.entry_kind.in_(("issue", "reserved_issue")) & (
        ~select(counter.id).where(counter.reverses_id == entry.id).exists()
    )


def _forecast_query(
    start: datetime | ColumnElement[datetime], end: datetime | ColumnElement[datetime], sqlite_wide: bool
):
    candidates, stock = _article_stock_query(
        select(WarehouseArticle).where(
            WarehouseArticle.is_active.is_(True), WarehouseArticle.stock_source.in_(("own", "material"))
        ),
        sqlite_wide,
    )
    own = WarehouseArticleLedgerEntry
    own_usage = (
        select(own.article_id, _scaled_sum(own.quantity, sqlite_wide).label("consumed"))
        .join(candidates, candidates.c.id == own.article_id)
        .where(active_article_issue(), own.created_at.between(start, end))
        .group_by(own.article_id)
        .subquery()
    )
    material = SmallPartLedgerEntry
    material_usage = (
        select(material.small_part_id, func.sum(material.physical_delta).label("physical_delta"))
        .join(candidates, candidates.c.small_part_id == material.small_part_id)
        .where(material.entry_kind == "issue", material.created_at.between(start, end))
        .group_by(material.small_part_id)
        .subquery()
    )
    return (
        stock.add_columns(
            candidates.c.name,
            candidates.c.sku,
            candidates.c.unit_code,
            own_usage.c.consumed,
            material_usage.c.physical_delta,
        )
        .outerjoin(own_usage, candidates.c.id == own_usage.c.article_id)
        .outerjoin(material_usage, candidates.c.small_part_id == material_usage.c.small_part_id)
    )


async def forecast_articles(session: AsyncSession, *, limit: int, offset: int) -> WarehouseForecastPage:
    now = datetime.now(timezone.utc)
    start = stock_timestamp_parameter(session, now - timedelta(days=FORECAST_WINDOW_DAYS))
    end = stock_timestamp_parameter(session, now)
    rows = await _execute_stock_sums(session, lambda sqlite_wide: _forecast_query(start, end, sqlite_wide))
    items = []
    for row in rows:
        if row.stock_source == "material":
            available = (row.material_physical or ZERO) - (row.material_reserved or ZERO)
            consumed = -(row.physical_delta or ZERO)
        else:
            available = (row.own_physical or ZERO) - (row.own_reserved or ZERO)
            consumed = row.consumed or ZERO

        days_until_minimum = None
        if available <= row.minimum_stock:
            days_until_minimum = 0
        elif available - consumed <= row.minimum_stock:
            days = (available - row.minimum_stock) * FORECAST_WINDOW_DAYS / consumed
            days_until_minimum = int(days.to_integral_value(rounding=ROUND_CEILING))

        # The observation window and projection horizon are equal, so the projected
        # balance uses the exact window total before the daily rate is rounded for display.
        items.append(
            WarehouseForecastRow(
                id=row.id,
                name=row.name,
                sku=row.sku,
                unit_code=row.unit_code,
                available=available,
                minimum_stock=row.minimum_stock,
                daily_usage=(consumed / FORECAST_WINDOW_DAYS).quantize(Decimal("0.00000001"))
                if consumed > ZERO
                else None,
                projected_available=max(ZERO, available - consumed) if consumed > ZERO else None,
                days_until_minimum=days_until_minimum,
            )
        )
    items.sort(
        key=lambda row: (
            row.days_until_minimum if row.days_until_minimum is not None else FORECAST_WINDOW_DAYS + 1,
            row.daily_usage is None,
            row.name.casefold(),
            row.id,
        )
    )
    return WarehouseForecastPage(
        items=items[offset : offset + limit],
        window_days=FORECAST_WINDOW_DAYS,
        total=len(items),
        limit=limit,
        offset=offset,
    )


async def usage_for_articles(session: AsyncSession, articles: list[WarehouseArticle]) -> dict[int, StockUsage]:
    result: dict[int, StockUsage] = {}
    material_ids = [article.small_part_id for article in articles if article.small_part_id is not None]
    material_usage = await usage_for_parts(session, material_ids)
    for article in articles:
        if article.small_part_id in material_usage:
            result[article.id] = material_usage[article.small_part_id]

    own_ids = [article.id for article in articles if article.stock_source == "own"]
    if own_ids:
        entry = WarehouseArticleLedgerEntry

        def query(sqlite_wide: bool):
            return (
                select(entry.article_id, func.max(entry.created_at), _scaled_sum(entry.quantity, sqlite_wide))
                .where(entry.article_id.in_(own_ids), active_article_issue())
                .group_by(entry.article_id)
            )

        rows = await _execute_stock_sums(session, query)
        result.update({identifier: StockUsage(last_used, quantity) for identifier, last_used, quantity in rows})
    return result


async def read_articles(session: AsyncSession, articles: list[WarehouseArticle]) -> list[WarehouseArticleRead]:
    usage = await usage_for_articles(session, articles)
    return [await read_article(session, article, usage.get(article.id, StockUsage())) for article in articles]


async def read_article(
    session: AsyncSession, article: WarehouseArticle, usage: StockUsage | None = None
) -> WarehouseArticleRead:
    locations = await location_balances(session, article)
    physical = sum((row.physical for row in locations), ZERO)
    reserved = sum((row.reserved for row in locations), ZERO)
    if usage is None:
        usage = (await usage_for_articles(session, [article])).get(article.id, StockUsage())
    material = await session.get(SmallPart, article.small_part_id) if article.small_part_id is not None else None
    return WarehouseArticleRead(
        **{key: getattr(article, key) for key in WarehouseArticleCreate.model_fields},
        id=article.id,
        version=article.version,
        created_at=article.created_at,
        updated_at=article.updated_at,
        stock_checked_at=material.stock_checked_at if material is not None else article.stock_checked_at,
        last_used_at=usage.last_used_at,
        consumed=usage.consumed,
        has_history=await has_history(session, article),
        locations=locations,
        balance=_article_balance(article.stock_source, article.minimum_stock, physical, reserved),
    )
