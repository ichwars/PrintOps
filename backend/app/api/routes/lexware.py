"""Lexware connection administration and explicit local master-data imports."""

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    RequireAnyPermissionIfAuthEnabled,
    RequirePermissionIfAuthEnabled,
    require_permission_if_auth_enabled,
    security,
)
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.lexware import LexwareConnection, LexwareResource
from backend.app.models.user import User
from backend.app.schemas.lexware import (
    ConnectionCreate,
    ConnectionRead,
    ConnectionTest,
    ConnectionUpdate,
    LexwareImportRequest,
    LexwarePreviewRequest,
    ResourceKind,
)
from backend.app.schemas.utc_timestamp import as_utc
from backend.app.services import lexware_connections as connections, lexware_imports as imports
from backend.app.services.lexware_client import LexwareError
from backend.app.services.lexware_sync import lexware_scheduler
from backend.app.services.order_errors import OrderDomainError, VersionConflictError
from backend.app.services.warehouse_articles import WarehouseError


class CredentialSafeRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                # Missing/extra fields can include the complete raw request in
                # Pydantic's `input`, before SecretStr has ever been validated.
                errors = [{key: item[key] for key in ("type", "loc", "msg") if key in item} for item in error.errors()]
                return JSONResponse(status_code=422, content={"detail": errors})

        return safe_handler


router = APIRouter(prefix="/lexware", tags=["lexware"], route_class=CredentialSafeRoute)


def _fail(error: LexwareError) -> NoReturn:
    status = error.status_code if error.status_code in {404, 409, 422} else 502
    raise HTTPException(status, detail={"code": error.code, "message": str(error)}) from None


def _read(connection: LexwareConnection) -> ConnectionRead:
    return ConnectionRead(
        **{field: getattr(connection, field) for field in ConnectionRead.model_fields if field != "connected"},
        connected=bool(connection.encrypted_api_key),
    )


async def _require(request: Request, *permissions: Permission) -> None:
    # Reuse the real auth dependency, including API-key scope checks; an API key
    # must not bypass a dynamic permission because its authenticated user is None.
    await require_permission_if_auth_enabled(*permissions)(
        credentials=await security(request), x_api_key=request.headers.get("X-API-Key")
    )


@router.get("/connections", response_model=list[ConnectionRead])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequireAnyPermissionIfAuthEnabled(
        Permission.ACCOUNTING_INTEGRATIONS_MANAGE,
        Permission.CUSTOMERS_READ,
        Permission.INVENTORY_READ,
        Permission.COMMERCIAL_DOCUMENTS_READ,
    ),
):
    return [_read(row) for row in (await db.scalars(select(LexwareConnection).order_by(LexwareConnection.id))).all()]


@router.post("/connections/test")
async def test_connection(
    body: ConnectionTest,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ACCOUNTING_INTEGRATIONS_MANAGE),
):
    try:
        return await connections.test_api_key(body.api_key.get_secret_value())
    except LexwareError as error:
        _fail(error)


@router.post("/connections", response_model=ConnectionRead, status_code=201)
async def create_connection(
    body: ConnectionCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ACCOUNTING_INTEGRATIONS_MANAGE),
):
    try:
        key = body.api_key.get_secret_value()
        encrypted = connections.encrypt_api_key(key)
        upstream = await connections.test_api_key(key)
        if upstream["organization_id"] != body.organization_id:
            raise LexwareError("Organization changed; test and confirm the connection again", 409)
        # Match profile deletion's SQLite writer lock / PostgreSQL profile row lock.
        # The upstream key check above must finish before this transaction begins.
        profile_is_active = await db.scalar(
            update(BusinessProfile)
            .where(BusinessProfile.id == body.business_profile_id)
            .values(version=BusinessProfile.version, updated_at=BusinessProfile.updated_at)
            .returning(BusinessProfile.is_active)
            .execution_options(synchronize_session=False)
        )
        if profile_is_active is not True:
            raise LexwareError("Business profile is unavailable", 409)
        connection = LexwareConnection(
            business_profile_id=body.business_profile_id, encrypted_api_key=encrypted, **upstream
        )
        db.add(connection)
        await db.commit()
        await db.refresh(connection)
        return _read(connection)
    except LexwareError as error:
        _fail(error)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            409, detail={"code": "duplicate_connection", "message": "Profile or organization already has a connection"}
        ) from None


@router.patch("/connections/{connection_id}", response_model=ConnectionRead)
async def update_connection(
    connection_id: int,
    body: ConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ACCOUNTING_INTEGRATIONS_MANAGE),
):
    try:
        # Test new credentials before acquiring a database write lock.
        upstream, encrypted = None, None
        if body.api_key is not None:
            encrypted = connections.encrypt_api_key(body.api_key.get_secret_value())
            upstream = await connections.test_api_key(body.api_key.get_secret_value())
        connection = await connections.lock_connection(db, connection_id)
        if upstream:
            if upstream["organization_id"] != connection.organization_id:
                raise LexwareError("A connection cannot change its Lexware organization", 409)
            connection.encrypted_api_key = encrypted
            connection.company_name = upstream["company_name"]
        if body.enabled is not None:
            if body.enabled and not connection.encrypted_api_key:
                raise LexwareError("An API key is required before enabling this connection", 409)
            connection.enabled = body.enabled
        connection.version += 1
        connection.last_error = None
        connection.sync_status = "idle" if connection.enabled else "paused"
        await db.commit()
        return _read(connection)
    except LexwareError as error:
        _fail(error)


@router.delete("/connections/{connection_id}", status_code=204)
async def disconnect_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ACCOUNTING_INTEGRATIONS_MANAGE),
):
    try:
        connection = await connections.lock_connection(db, connection_id)
        connection.encrypted_api_key = None
        connection.enabled = False
        connection.version += 1
        connection.sync_status = "disconnected"
        connection.last_error = None
        await db.commit()
    except LexwareError as error:
        _fail(error)


@router.post("/connections/{connection_id}/sync", status_code=202)
async def queue_sync(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ACCOUNTING_INTEGRATIONS_MANAGE),
):
    try:
        connection = await connections.lock_connection(db, connection_id)
        if not connection.enabled or not connection.encrypted_api_key:
            raise LexwareError("Enable and connect Lexware before synchronizing", 409)
        connection.sync_status = "queued"
        await db.commit()
        lexware_scheduler.queue(connection_id)
        return {"status": "queued"}
    except LexwareError as error:
        _fail(error)


@router.get("/connections/{connection_id}/resources")
async def list_resources(
    connection_id: int,
    request: Request,
    kind: ResourceKind = Query(),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequireAnyPermissionIfAuthEnabled(Permission.CUSTOMERS_READ, Permission.INVENTORY_READ),
):
    await _require(request, Permission.CUSTOMERS_READ if kind == "contacts" else Permission.INVENTORY_READ)
    rows = (
        await db.scalars(
            select(LexwareResource)
            .where(LexwareResource.connection_id == connection_id, LexwareResource.kind == kind)
            .order_by(LexwareResource.id)
        )
    ).all()
    return [
        {
            "id": row.id,
            "external_id": row.external_id,
            "name": (
                (row.payload.get("company") or {}).get("name")
                or " ".join(
                    filter(
                        None,
                        (
                            (row.payload.get("person") or {}).get("firstName"),
                            (row.payload.get("person") or {}).get("lastName"),
                        ),
                    )
                )
            )
            if kind == "contacts"
            else row.payload.get("title", ""),
            "number": str(((row.payload.get("roles") or {}).get("customer") or {}).get("number", ""))
            if kind == "contacts"
            else row.payload.get("articleNumber", ""),
            "archived": bool(row.payload.get("archived")),
            "version_hash": row.version_hash,
            "customer_id": row.customer_id,
            "article_id": row.article_id,
            "payload": row.payload,
            "updated_at": as_utc(row.updated_at),
        }
        for row in rows
    ]


@router.post("/connections/{connection_id}/preview")
async def preview_import(
    connection_id: int,
    body: LexwarePreviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ACCOUNTING_INTEGRATIONS_MANAGE),
):
    try:
        resource = await imports.resource_for(db, connection_id, body.resource_id)
        await _require(request, Permission.CUSTOMERS_READ if resource.kind == "contacts" else Permission.INVENTORY_READ)
        return await imports.preview(db, connection_id, body)
    except LexwareError as error:
        _fail(error)
    except OrderDomainError:
        raise HTTPException(404, detail={"code": "not_found", "message": "Local import target not found"}) from None


@router.post("/connections/{connection_id}/import")
async def import_resource(
    connection_id: int,
    body: LexwareImportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ACCOUNTING_INTEGRATIONS_MANAGE),
):
    try:
        resource = await imports.resource_for(db, connection_id, body.resource_id)
        if resource.kind == "contacts":
            await _require(request, Permission.CUSTOMERS_READ, Permission.CUSTOMERS_MANAGE)
        else:
            write_permission = (
                Permission.INVENTORY_UPDATE if body.article_id or resource.article_id else Permission.INVENTORY_CREATE
            )
            await _require(request, Permission.INVENTORY_READ, write_permission)
        # Release the read snapshot before obtaining the transaction's writer lock.
        await db.rollback()
        result = await imports.apply_import(db, connection_id, body)
        await db.commit()
        return result
    except LexwareError as error:
        _fail(error)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            409,
            detail={"code": "import_conflict", "message": "This record is already linked or conflicts with local data"},
        ) from None
    except WarehouseError as error:
        await db.rollback()
        raise HTTPException(
            error.status,
            detail={"code": error.code, "message": str(error)},
        ) from None
    except VersionConflictError:
        raise HTTPException(
            409, detail={"code": "version_conflict", "message": "Local data changed; refresh the preview"}
        ) from None
    except (OrderDomainError, ValueError):
        raise HTTPException(
            422, detail={"code": "invalid_import", "message": "Selected data cannot be imported into this local record"}
        ) from None
