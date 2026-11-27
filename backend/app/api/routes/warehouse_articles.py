from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

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
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry
from backend.app.models.user import User
from backend.app.models.warehouse_article import WarehouseArticle, WarehouseArticleLedgerEntry
from backend.app.schemas.inventory_stocktake import StockCheckRead, StockCheckRequest
from backend.app.schemas.warehouse_article import (
    ArticleKind,
    StockSource,
    WarehouseArticleCreate,
    WarehouseArticlePage,
    WarehouseArticleRead,
    WarehouseArticleUpdate,
    WarehouseForecastPage,
    WarehouseMovementCreate,
    WarehouseMovementRead,
    WarehouseReservationRead,
)
from backend.app.services import inventory_stocktake, warehouse_articles as service
from backend.app.services.small_parts import StockUsage
from backend.app.services.warehouse_stock import open_reservations, post_movement

router = APIRouter(prefix="/warehouse-articles", tags=["warehouse-articles"])


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
    article_id: int | None = Query(None, gt=0, le=2147483647),
    q: str = Query("", max_length=255),
    active: bool | None = None,
    kind: ArticleKind | None = None,
    stock_source: StockSource | None = None,
    usage: Literal["used", "new"] | None = None,
    location_id: int | None = Query(None, gt=0),
    unit_code: str | None = Query(None, min_length=1, max_length=16),
    low_stock: bool = False,
    sort_by: Literal[
        "id",
        "sku",
        "name",
        "kind",
        "physical",
        "reserved",
        "available",
        "minimum_stock",
        "created_at",
        "last_used_at",
        "consumed",
        "remaining",
        "stock_checked_at",
        "stock_source",
        "is_active",
        "unit_cost",
        "sale_price",
        "updated_at",
    ]
    | None = None,
    sort_dir: Literal["asc", "desc"] = "asc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    statement = select(WarehouseArticle)
    if q.strip():
        statement = statement.where(
            or_(
                WarehouseArticle.name.icontains(q.strip(), autoescape=True),
                WarehouseArticle.sku.icontains(q.strip(), autoescape=True),
                WarehouseArticle.description.icontains(q.strip(), autoescape=True),
            )
        )
    for column, value in (
        (WarehouseArticle.id, article_id),
        (WarehouseArticle.is_active, active),
        (WarehouseArticle.kind, kind),
        (WarehouseArticle.stock_source, stock_source),
        (WarehouseArticle.unit_code, unit_code),
    ):
        if value is not None:
            statement = statement.where(column == value)
    if usage:
        own_issue = (
            select(WarehouseArticleLedgerEntry.id)
            .where(
                WarehouseArticleLedgerEntry.article_id == WarehouseArticle.id,
                service.active_article_issue(),
            )
            .exists()
        )
        material_issue = (
            select(SmallPartLedgerEntry.id)
            .where(
                SmallPartLedgerEntry.small_part_id == WarehouseArticle.small_part_id,
                SmallPartLedgerEntry.entry_kind == "issue",
            )
            .exists()
        )
        has_usage = or_(own_issue, material_issue)
        statement = statement.where(
            WarehouseArticle.stock_source != "none", has_usage if usage == "used" else ~has_usage
        )
    if location_id is not None:
        entry = WarehouseArticleLedgerEntry
        own_balance = (
            select(
                func.sum(case((entry.location_id == location_id, entry.physical_delta), else_=-entry.physical_delta))
            )
            .where(
                entry.article_id == WarehouseArticle.id,
                or_(entry.location_id == location_id, entry.target_location_id == location_id),
            )
            .scalar_subquery()
        )
        material_location = (
            select(SmallPart.id)
            .where(
                SmallPart.id == WarehouseArticle.small_part_id,
                SmallPart.location_id == location_id,
            )
            .exists()
        )
        statement = statement.where(or_(own_balance > 0, material_location))
    fields = {
        "id": WarehouseArticle.id,
        "sku": func.lower(WarehouseArticle.sku),
        "name": func.lower(WarehouseArticle.name),
        "kind": WarehouseArticle.kind,
        "minimum_stock": case((WarehouseArticle.kind != "service", WarehouseArticle.minimum_stock)),
        "created_at": WarehouseArticle.created_at,
        "updated_at": WarehouseArticle.updated_at,
        "stock_source": WarehouseArticle.stock_source,
        "is_active": WarehouseArticle.is_active,
        "unit_cost": WarehouseArticle.unit_cost,
        "sale_price": WarehouseArticle.sale_price,
        "stock_checked_at": case(
            (
                WarehouseArticle.stock_source == "material",
                select(SmallPart.stock_checked_at)
                .where(SmallPart.id == WarehouseArticle.small_part_id)
                .scalar_subquery(),
            ),
            else_=WarehouseArticle.stock_checked_at,
        ),
    }
    field = fields.get(sort_by)
    order = [WarehouseArticle.name.asc(), WarehouseArticle.id.asc()]
    if field is not None:
        order.insert(0, (field.desc() if sort_dir == "desc" else field.asc()).nulls_last())
    async with _errors(db):
        if sort_by in ("physical", "reserved", "available", "remaining", "consumed", "last_used_at"):
            balances = await service.balances_for_listing(db, statement)
            stocked = [
                (article_id, balance)
                for article_id, balance in balances
                if balance is not None and (not low_stock or balance.is_low_stock)
            ]
            if sort_by in ("consumed", "last_used_at"):
                usage = await service.usage_for_articles(db, list(await db.scalars(statement)))
                dated = [row for row in stocked if sort_by == "consumed" or row[0] in usage]
                dated.sort(
                    key=lambda row: getattr(usage.get(row[0], StockUsage()), sort_by),
                    reverse=sort_dir == "desc",
                )
                stocked = dated + [row for row in stocked if sort_by == "last_used_at" and row[0] not in usage]
            else:
                attribute = "physical" if sort_by == "remaining" else sort_by
                stocked.sort(key=lambda row: getattr(row[1], attribute), reverse=sort_dir == "desc")
            identifiers = [article_id for article_id, _ in stocked]
            if not low_stock:
                identifiers.extend(article_id for article_id, balance in balances if balance is None)
            page_ids = identifiers[offset : offset + limit]
            articles = (
                {
                    article.id: article
                    for article in await db.scalars(statement.where(WarehouseArticle.id.in_(page_ids)))
                }
                if page_ids
                else {}
            )
            return WarehouseArticlePage(
                items=await service.read_articles(
                    db, [articles[article_id] for article_id in page_ids if article_id in articles]
                ),
                total=len(identifiers),
                limit=limit,
                offset=offset,
            )
        if low_stock:
            articles = list(await db.scalars(statement.order_by(*order)))
            rows = await service.read_articles(db, articles)
            rows = [row for row in rows if row.balance.is_low_stock]
            return WarehouseArticlePage(
                items=rows[offset : offset + limit], total=len(rows), limit=limit, offset=offset
            )
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        articles = list(await db.scalars(statement.order_by(*order).offset(offset).limit(limit)))
        return WarehouseArticlePage(
            items=await service.read_articles(db, articles),
            total=total,
            limit=limit,
            offset=offset,
        )


@router.get("/forecast", response_model=WarehouseForecastPage)
async def warehouse_forecast(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> WarehouseForecastPage:
    async with _errors(db):
        return await service.forecast_articles(db, limit=limit, offset=offset)


@router.post("/stock-check", response_model=StockCheckRead)
async def confirm_warehouse_stock_check(
    data: StockCheckRequest,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
) -> StockCheckRead:
    checked_at = datetime.now(timezone.utc)
    ids = sorted(set(data.ids))
    async with _errors(db):
        articles = []
        for offset in range(0, len(ids), 500):
            articles.extend(
                await db.scalars(
                    select(WarehouseArticle)
                    .where(WarehouseArticle.id.in_(ids[offset : offset + 500]))
                    .order_by(WarehouseArticle.id)
                    .with_for_update()
                )
            )
        if len(articles) != len(ids) or any(
            not article.is_active or article.stock_source == "none" for article in articles
        ):
            raise service.WarehouseError("stock_check_unavailable", "Bestand kann nicht geprüft werden")
        await inventory_stocktake.mark_checked(
            db,
            WarehouseArticle,
            [article.id for article in articles if article.stock_source == "own"],
            checked_at,
            WarehouseArticle.is_active.is_(True),
            WarehouseArticle.stock_source == "own",
        )
        await inventory_stocktake.mark_checked(
            db,
            SmallPart,
            [article.small_part_id for article in articles if article.small_part_id is not None],
            checked_at,
            SmallPart.is_active.is_(True),
        )
        await db.commit()
    return StockCheckRead(stock_checked_at=checked_at)


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
