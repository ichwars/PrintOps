from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    statement = select(WarehouseArticle).order_by(WarehouseArticle.name, WarehouseArticle.id)
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
        return WarehouseArticlePage(items=rows[offset : offset + limit], total=len(rows), limit=limit, offset=offset)


@router.post("", response_model=WarehouseArticleRead, status_code=201)
async def create_article(
    data: WarehouseArticleCreate,
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    async with _errors(db):
        return await service.read_article(db, await service.load_article(db, article_id))


@router.patch("/{article_id}", response_model=WarehouseArticleRead)
async def update_article(
    article_id: int,
    data: WarehouseArticleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    async with _errors(db):
        article = await service.update_article(db, article_id, data)
        response = await service.read_article(db, article)
        await db.commit()
        return response


@router.delete("/{article_id}", response_model=WarehouseArticleRead)
async def archive_article(
    article_id: int,
    version: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    async with _errors(db):
        await service.load_article(db, article_id)
        return await open_reservations(db, article_id)


@router.post("/{article_id}/ledger", response_model=WarehouseMovementRead, status_code=201)
async def add_movement(
    article_id: int,
    data: WarehouseMovementCreate,
    db: AsyncSession = Depends(get_db),
    user: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    async with _errors(db):
        entry = await post_movement(db, article_id, data, actor_id=user.id if user else None)
        response = WarehouseMovementRead.model_validate(entry)
        await db.commit()
        return response
