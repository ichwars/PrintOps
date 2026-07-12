from __future__ import annotations

from collections import deque
from collections.abc import Awaitable
from pathlib import Path
from typing import NoReturn, TypeVar

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequireAnyPermissionIfAuthEnabled, RequirePermissionIfAuthEnabled
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.user import User
from backend.app.schemas.business_profile import (
    BusinessProfileCreate,
    BusinessProfileOption,
    BusinessProfileResponse,
    BusinessProfileUpdate,
)
from backend.app.services import business_profile as business_profile_service
from backend.app.services.business_profile_logo import (
    MAX_LOGO_BYTES,
    InvalidBusinessProfileLogo,
    logo_path,
    remove_logo,
    validate_logo,
    write_logo_atomic,
)
from backend.app.services.order_errors import (
    DuplicateBusinessKeyError,
    OrderDomainError,
    ResourceInUseError,
    ResourceNotFoundError,
    VersionConflictError,
)

router = APIRouter(prefix="/business-profiles", tags=["business-profiles"])

_DUPLICATE_MESSAGE = "A business profile with this name already exists"
_TAX_DUPLICATE_MESSAGE = "A duplicate tax identifier already exists"
_GENERIC_INTEGRITY_MESSAGE = "The business profile conflicts with existing data"
_DEFAULT_CONFLICT_MESSAGE = "The default business profile changed concurrently; retry the request"
_DELETE_REFERENCE_MESSAGE = "The business profile is referenced and cannot be deleted"
_T = TypeVar("_T")


def _stored_logo_path(profile) -> Path | None:
    if profile.logo_media_type is None or profile.logo_version is None:
        return None
    return logo_path(
        settings.business_profile_logo_dir,
        profile_id=profile.id,
        version=profile.logo_version,
        media_type=profile.logo_media_type,
    )


def _raise_http_error(error: OrderDomainError) -> NoReturn:
    if isinstance(error, ResourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        code = "not_found"
    elif isinstance(error, VersionConflictError):
        status_code = status.HTTP_409_CONFLICT
        code = "version_conflict"
    elif isinstance(error, ResourceInUseError):
        status_code = status.HTTP_409_CONFLICT
        code = "resource_in_use"
    elif isinstance(error, DuplicateBusinessKeyError):
        status_code = status.HTTP_409_CONFLICT
        code = "duplicate_business_key"
    else:
        raise error

    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
    )


def _integrity_error_sources(error: IntegrityError) -> tuple[BaseException, ...]:
    pending = deque([error.orig])
    sources: list[BaseException] = []
    seen: set[int] = set()

    while pending and len(sources) < 16:
        source = pending.popleft()
        if source is None or id(source) in seen:
            continue
        seen.add(id(source))
        sources.append(source)
        pending.extend((getattr(source, "__cause__", None), getattr(source, "__context__", None)))

    return tuple(sources)


def _error_metadata(sources: tuple[BaseException, ...], *attribute_names: str) -> set[str]:
    values: set[str] = set()
    for source in sources:
        for metadata_source in (source, getattr(source, "diag", None)):
            if metadata_source is None:
                continue
            for attribute_name in attribute_names:
                value = getattr(metadata_source, attribute_name, None)
                if isinstance(value, str):
                    values.add(value.casefold())
    return values


def _classify_integrity_error(
    error: IntegrityError,
    *,
    operation_kind: str,
) -> OrderDomainError | None:
    sources = _integrity_error_sources(error)
    message = " ".join(str(source) for source in sources).casefold()
    constraint_names = _error_metadata(sources, "constraint_name")
    sql_states = _error_metadata(sources, "sqlstate", "pgcode")

    is_foreign_key_error = (
        "23503" in sql_states
        or "foreign key constraint failed" in message
        or "violates foreign key constraint" in message
    )
    if operation_kind == "delete" and is_foreign_key_error:
        return ResourceInUseError(_DELETE_REFERENCE_MESSAGE)

    if "uq_business_profiles_single_default" in constraint_names or "business_profiles.is_default" in message:
        return VersionConflictError(_DEFAULT_CONFLICT_MESSAGE)

    if (
        "uq_business_profile_tax_identifier" in constraint_names
        or "business_profile_tax_identifiers.business_profile_id" in message
    ):
        return DuplicateBusinessKeyError(_TAX_DUPLICATE_MESSAGE)

    if (
        constraint_names & {"business_profiles_name_key", "uq_business_profiles_name"}
        or "business_profiles.name" in message
    ):
        return DuplicateBusinessKeyError(_DUPLICATE_MESSAGE)

    is_unique_error = (
        "23505" in sql_states
        or "unique constraint failed" in message
        or "duplicate key value violates unique constraint" in message
    )
    if is_unique_error:
        return DuplicateBusinessKeyError(_GENERIC_INTEGRITY_MESSAGE)
    return None


async def _commit_write(
    session: AsyncSession,
    operation: Awaitable[_T],
    *,
    operation_kind: str = "write",
) -> _T:
    try:
        result = await operation
        await session.commit()
        return result
    except IntegrityError as exc:
        await session.rollback()
        classified = _classify_integrity_error(exc, operation_kind=operation_kind)
        if classified is None:
            raise
        raise classified from exc
    except OrderDomainError:
        await session.rollback()
        raise


@router.get("/", response_model=list[BusinessProfileResponse])
async def list_business_profiles(
    include_inactive: bool = Query(default=False, alias="includeInactive"),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_SETTINGS_READ),
):
    return await business_profile_service.list_business_profiles(
        db,
        include_inactive=include_inactive,
    )


@router.get("/options", response_model=list[BusinessProfileOption])
async def list_business_profile_options(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequireAnyPermissionIfAuthEnabled(
        Permission.CUSTOMERS_READ,
        Permission.CALCULATIONS_READ,
        Permission.ORDERS_READ,
        Permission.COMMERCIAL_DOCUMENTS_READ,
    ),
):
    profiles = await business_profile_service.list_business_profiles(db)
    return [
        BusinessProfileOption(
            id=profile.id,
            name=profile.name,
            country_code=profile.country_code,
            default_currency=profile.default_currency,
            timezone=profile.timezone,
            default_locale=profile.default_locale,
            billing_mode=profile.billing_mode,
            is_default=profile.is_default,
            is_active=profile.is_active,
        )
        for profile in profiles
    ]


@router.post("/", response_model=BusinessProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_business_profile(
    data: BusinessProfileCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_SETTINGS_MANAGE),
):
    try:
        return await _commit_write(
            db,
            business_profile_service.create_business_profile(db, data),
        )
    except OrderDomainError as exc:
        _raise_http_error(exc)


@router.get("/{profile_id}", response_model=BusinessProfileResponse)
async def get_business_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_SETTINGS_READ),
):
    try:
        return await business_profile_service.get_business_profile(db, profile_id)
    except OrderDomainError as exc:
        _raise_http_error(exc)


@router.get("/{profile_id}/logo")
async def get_business_profile_logo(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_SETTINGS_READ),
):
    try:
        profile = await business_profile_service.get_business_profile(db, profile_id)
    except OrderDomainError as exc:
        _raise_http_error(exc)
    path = _stored_logo_path(profile)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Logo not found"})
    return FileResponse(
        path, media_type=profile.logo_media_type, headers={"Cache-Control": "private, max-age=31536000, immutable"}
    )


@router.put("/{profile_id}/logo", response_model=BusinessProfileResponse)
async def upload_business_profile_logo(
    profile_id: int,
    version: int = Query(ge=1),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_SETTINGS_MANAGE),
):
    content = await file.read(MAX_LOGO_BYTES + 1)
    try:
        media_type = validate_logo(content, file.content_type)
        profile = await business_profile_service.get_business_profile(db, profile_id)
        old_path = _stored_logo_path(profile)
        new_version = version + 1
        new_path = logo_path(
            settings.business_profile_logo_dir, profile_id=profile_id, version=new_version, media_type=media_type
        )
        cas = await db.execute(
            update(BusinessProfile)
            .where(BusinessProfile.id == profile_id, BusinessProfile.version == version)
            .values(logo_media_type=media_type, logo_version=new_version, version=new_version)
            .returning(BusinessProfile.id)
        )
        if cas.scalar_one_or_none() is None:
            raise VersionConflictError(f"Business profile {profile_id} changed concurrently; reload it and retry")
        write_logo_atomic(new_path, content)
        try:
            await db.commit()
        except Exception:
            remove_logo(new_path)
            raise
        if old_path is not None and old_path != new_path:
            remove_logo(old_path)
        return await business_profile_service.get_business_profile(db, profile_id)
    except InvalidBusinessProfileLogo as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc), "message": str(exc)}) from exc
    except OrderDomainError as exc:
        await db.rollback()
        _raise_http_error(exc)


@router.delete("/{profile_id}/logo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_business_profile_logo(
    profile_id: int,
    version: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_SETTINGS_MANAGE),
) -> Response:
    try:
        profile = await business_profile_service.get_business_profile(db, profile_id)
        old_path = _stored_logo_path(profile)
        cas = await db.execute(
            update(BusinessProfile)
            .where(BusinessProfile.id == profile_id, BusinessProfile.version == version)
            .values(logo_media_type=None, logo_version=None, version=version + 1)
            .returning(BusinessProfile.id)
        )
        if cas.scalar_one_or_none() is None:
            raise VersionConflictError(f"Business profile {profile_id} changed concurrently; reload it and retry")
        await db.commit()
        if old_path is not None:
            remove_logo(old_path)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except OrderDomainError as exc:
        await db.rollback()
        _raise_http_error(exc)


@router.put("/{profile_id}", response_model=BusinessProfileResponse)
async def update_business_profile(
    profile_id: int,
    data: BusinessProfileUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_SETTINGS_MANAGE),
):
    try:
        return await _commit_write(
            db,
            business_profile_service.update_business_profile(db, profile_id, data),
        )
    except OrderDomainError as exc:
        _raise_http_error(exc)


@router.post("/{profile_id}/default", response_model=BusinessProfileResponse)
async def set_default_business_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_SETTINGS_MANAGE),
):
    try:
        return await _commit_write(
            db,
            business_profile_service.set_default_business_profile(db, profile_id),
        )
    except OrderDomainError as exc:
        _raise_http_error(exc)


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_business_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.ORDER_SETTINGS_MANAGE),
) -> Response:
    try:
        profile = await business_profile_service.get_business_profile(db, profile_id)
        old_logo_path = _stored_logo_path(profile)
        await _commit_write(
            db,
            business_profile_service.delete_business_profile(db, profile_id),
            operation_kind="delete",
        )
        if old_logo_path is not None:
            remove_logo(old_logo_path)
    except OrderDomainError as exc:
        _raise_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
