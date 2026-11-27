from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    RequirePermissionIfAuthEnabled,
    require_permission_if_auth_enabled,
    security,
)
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.models.small_part import SmallPartLedgerEntry
from backend.app.models.user import User
from backend.app.models.warehouse_article import WarehouseArticle, WarehouseArticleLedgerEntry
from backend.app.schemas.warehouse_article import (
    ArticleKind,
    StockSource,
    WarehouseArticleCreate,
    WarehouseArticlePage,
    WarehouseArticleRead,
    WarehouseArticleUpdate,
    WarehouseMovementCreate,
    WarehouseMovementRead,
    WarehouseReservationRead,
)
from backend.app.services import warehouse_articles as service
from backend.app.services.warehouse_stock import open_reservations, post_movement

router = APIRouter(prefix="/warehouse-articles", tags=["warehouse-articles"])


def _own_ledger_total(delta, *, exclude_transfers: bool = False):
    """Journal sum for an own-stock article. Transfers only move stock between the
    article's locations, so their physical_delta nets out via target_location_id
    (mirrors services.warehouse_articles.location_balances)."""
    if exclude_transfers:
        delta = case((WarehouseArticleLedgerEntry.target_location_id.is_(None), delta), else_=0)
    return (
        select(func.coalesce(func.sum(delta), 0))
        .where(WarehouseArticleLedgerEntry.article_id == WarehouseArticle.id)
        .correlate(WarehouseArticle)
        .scalar_subquery()
    )


def _material_ledger_total(delta):
    return (
        select(func.coalesce(func.sum(delta), 0))
        .where(SmallPartLedgerEntry.small_part_id == WarehouseArticle.small_part_id)
        .correlate(WarehouseArticle)
        .scalar_subquery()
    )


def _balance_expression(own_delta, material_delta, *, exclude_transfers: bool = False):
    # Decision: balance columns stay sortable in the paginated DB query via correlated
    # subqueries that reproduce the Python balance of services.warehouse_articles.read_article
    # exactly: own stock sums warehouse_article_ledger_entries, material stock mirrors the
    # linked small_parts journal (small_parts.get_balance), services carry no stock (0).
    return case(
        (
            WarehouseArticle.stock_source == "own",
            _own_ledger_total(own_delta, exclude_transfers=exclude_transfers),
        ),
        (WarehouseArticle.stock_source == "material", _material_ledger_total(material_delta)),
        else_=0,
    )


_PHYSICAL = _balance_expression(
    WarehouseArticleLedgerEntry.physical_delta, SmallPartLedgerEntry.physical_delta, exclude_transfers=True
)
_RESERVED = _balance_expression(WarehouseArticleLedgerEntry.reserved_delta, SmallPartLedgerEntry.reserved_delta)

_SORTABLE_COLUMNS = {
    "sku": WarehouseArticle.sku,
    "name": WarehouseArticle.name,
    "kind": WarehouseArticle.kind,
    "stock_source": WarehouseArticle.stock_source,
    "is_active": WarehouseArticle.is_active,
    "minimum_stock": WarehouseArticle.minimum_stock,
    "unit_cost": WarehouseArticle.unit_cost,
    "sale_price": WarehouseArticle.sale_price,
    "created_at": WarehouseArticle.created_at,
    "updated_at": WarehouseArticle.updated_at,
    "physical": _PHYSICAL,
    "reserved": _RESERVED,
    "available": _PHYSICAL - _RESERVED,
}

_BALANCE_SORT_KEYS = frozenset({"physical", "reserved", "available"})


@asynccontextmanager
async def _errors(db: AsyncSession):
    try:
        yield
    except service.WarehouseError as exc:
        await db.rollback()
        raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            409,
            detail={
                "code": "conflict",
                "message": "Artikelnummer, Materialzuordnung oder Buchung bereits vorhanden; Referenzen prüfen",
            },
        ) from exc
    except OperationalError as exc:
        await db.rollback()
        if "locked" not in str(exc).lower() and "deadlock" not in str(exc).lower():
            raise
        raise HTTPException(
            409,
            detail={
                "code": "stock_busy",
                "message": "Parallelbuchung läuft. Mit demselben Buchungsschlüssel erneut versuchen",
            },
        ) from exc


@router.get("", response_model=WarehouseArticlePage)
async def list_articles(
    q: str = Query("", max_length=255),
    active: bool | None = None,
    kind: ArticleKind | None = None,
    stock_source: StockSource | None = None,
    low_stock: bool = False,
    sort_by: str = Query("name"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    column = _SORTABLE_COLUMNS.get(sort_by)
    if column is None:
        raise HTTPException(400, f"Cannot sort by {sort_by!r}")
    ordering = column.asc() if sort_dir == "asc" else column.desc()
    statement = select(WarehouseArticle).order_by(ordering, WarehouseArticle.id)
    if q.strip():
        statement = statement.where(
            or_(
                WarehouseArticle.name.icontains(q.strip(), autoescape=True),
                WarehouseArticle.sku.icontains(q.strip(), autoescape=True),
                WarehouseArticle.description.icontains(q.strip(), autoescape=True),
            )
        )
    for column, value in (
        (WarehouseArticle.is_active, active),
        (WarehouseArticle.kind, kind),
        (WarehouseArticle.stock_source, stock_source),
    ):
        if value is not None:
            statement = statement.where(column == value)
    async with _errors(db):
        if not low_stock:
            total = await db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
            articles = list(await db.scalars(statement.offset(offset).limit(limit)))
            return WarehouseArticlePage(
                items=[await service.read_article(db, article) for article in articles],
                total=total,
                limit=limit,
                offset=offset,
            )
        articles = list(await db.scalars(statement))
        rows = [await service.read_article(db, article) for article in articles]
        if low_stock:
            rows = [row for row in rows if row.balance.is_low_stock]
            if sort_by in _BALANCE_SORT_KEYS:
                # This branch loads all rows and filters in Python, so balance sorting
                # is re-applied on the serialized rows (stable sort keeps the query's
                # id tiebreaker for equal balances).
                rows.sort(key=lambda row: getattr(row.balance, sort_by), reverse=sort_dir == "desc")
        return WarehouseArticlePage(items=rows[offset : offset + limit], total=len(rows), limit=limit, offset=offset)


@router.post("", response_model=WarehouseArticleRead, status_code=201)
async def create_article(
    data: WarehouseArticleCreate,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE),
):
    async with _errors(db):
        article = await service.create_article(db, data)
        response = await service.read_article(db, article)
        await db.commit()
        return response


@router.get("/{article_id}", response_model=WarehouseArticleRead)
async def get_article(
    article_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    async with _errors(db):
        return await service.read_article(db, await service.load_article(db, article_id))


@router.patch("/{article_id}", response_model=WarehouseArticleRead)
async def update_article(
    article_id: int,
    data: WarehouseArticleUpdate,
    request: Request,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    if data.is_active is False:
        await require_permission_if_auth_enabled(Permission.INVENTORY_DELETE)(
            credentials=await security(request), x_api_key=request.headers.get("X-API-Key")
        )
    async with _errors(db):
        article = await service.update_article(db, article_id, data)
        response = await service.read_article(db, article)
        await db.commit()
        return response


@router.delete("/{article_id}", response_model=WarehouseArticleRead)
async def archive_article(
    article_id: int,
    version: int = Query(..., gt=0),
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_DELETE),
):
    # Never physically remove a referenced article or its journal.
    async with _errors(db):
        article = await service.update_article(db, article_id, WarehouseArticleUpdate(version=version, is_active=False))
        response = await service.read_article(db, article)
        await db.commit()
        return response


@router.get("/{article_id}/ledger", response_model=list[WarehouseMovementRead])
async def list_ledger(
    article_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    async with _errors(db):
        await service.load_article(db, article_id)
        return list(
            await db.scalars(
                select(WarehouseArticleLedgerEntry)
                .where(WarehouseArticleLedgerEntry.article_id == article_id)
                .order_by(WarehouseArticleLedgerEntry.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )


@router.get("/{article_id}/reservations", response_model=list[WarehouseReservationRead])
async def list_reservations(
    article_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    async with _errors(db):
        await service.load_article(db, article_id)
        return await open_reservations(db, article_id)


@router.post("/{article_id}/ledger", response_model=WarehouseMovementRead, status_code=201)
async def add_movement(
    article_id: int,
    data: WarehouseMovementCreate,
    db: AsyncSession = DB_SESSION,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    async with _errors(db):
        entry = await post_movement(db, article_id, data, actor_id=user.id if user else None)
        response = WarehouseMovementRead.model_validate(entry)
        await db.commit()
        return response
