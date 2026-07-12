from decimal import Decimal
from pathlib import Path
from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.config import settings as app_settings
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.user import User
from backend.app.schemas.calculation import (
    CalculationApprove,
    CalculationBatchPreviewInput,
    CalculationCreate,
    CalculationDetail,
    CalculationListResponse,
    CalculationPreviewInput,
    CalculationPreviewRead,
    CalculationRevisionRead,
    CalculationTemplateCreate,
    CalculationTemplateRead,
    CalculationUpdate,
)
from backend.app.services import calculation as calculation_service
from backend.app.services.calculation_engine import (
    LaborCostInput,
    VariantCostInputs,
    calculate_combined,
    calculate_variant,
)
from backend.app.services.order_errors import OrderDomainError, ResourceNotFoundError, VersionConflictError
from backend.app.services.slicer_3mf_convert import count_plates_in_3mf
from backend.app.utils.threemf_tools import extract_filament_usage_from_3mf, extract_print_time_from_3mf

router = APIRouter(prefix="/calculations", tags=["calculations"])


def _preview_inputs(data: CalculationPreviewInput) -> VariantCostInputs:
    values = data.model_dump(
        exclude={"labor", "acquisition_value", "residual_value", "service_years", "annual_hours", "maintenance_rate"}
    )
    if data.acquisition_value is not None and data.service_years is not None and data.annual_hours is not None:
        depreciable = max(Decimal("0"), data.acquisition_value - data.residual_value)
        values["machine_cost_per_hour"] = depreciable / (data.service_years * data.annual_hours) * (
            Decimal("1") + data.maintenance_rate
        )
    values["labor"] = tuple(LaborCostInput(entry.hours, entry.hourly_rate, entry.allocation_basis) for entry in data.labor)
    return VariantCostInputs(**values)


def _raise_http(error: OrderDomainError) -> NoReturn:
    if isinstance(error, ResourceNotFoundError):
        code, status_code = "not_found", status.HTTP_404_NOT_FOUND
    elif isinstance(error, VersionConflictError):
        code, status_code = "version_conflict", status.HTTP_409_CONFLICT
    else:
        code, status_code = "invalid_calculation", status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail={"code": code, "message": str(error)})


def _detail(calculation) -> CalculationDetail:
    detail = CalculationDetail.model_validate(calculation)
    current = max(calculation.revisions, key=lambda item: item.revision_number, default=None)
    if current is None:
        return detail
    return detail.model_copy(
        update={
            "current_revision": current.revision_number,
            "production_cost": current.production_cost,
            "selling_price": current.selling_price,
        }
    )


@router.post("/preview", response_model=CalculationPreviewRead)
async def preview_calculation(
    data: CalculationPreviewInput,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_READ),
) -> CalculationPreviewRead:
    return CalculationPreviewRead.model_validate(calculate_variant(_preview_inputs(data)), from_attributes=True)


@router.post("/source-files", status_code=status.HTTP_201_CREATED)
async def upload_calculation_source(
    file: UploadFile = File(...),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_UPDATE),
) -> dict:
    from backend.app.api.routes.library import validate_print_file_upload

    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".3mf"):
        raise HTTPException(status_code=400, detail="Calculation source must be a .3mf file")
    content = await file.read()
    validate_print_file_upload(filename, content)
    target_dir = app_settings.base_dir / "calculations" / "sources"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}.3mf"
    target.write_bytes(content)
    filaments = extract_filament_usage_from_3mf(target)
    return {
        "source_file": target.relative_to(app_settings.base_dir).as_posix(), "filename": filename,
        "size_bytes": len(content), "plate_count": count_plates_in_3mf(content),
        "print_time_seconds": extract_print_time_from_3mf(target),
        "material_grams": sum(float(item.get("used_g", 0)) for item in filaments), "filaments": filaments,
    }


@router.post("/preview-batch", response_model=CalculationPreviewRead)
async def preview_calculation_batch(
    data: CalculationBatchPreviewInput,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_READ),
) -> CalculationPreviewRead:
    combined = calculate_combined([_preview_inputs(operation) for operation in data.operations], _preview_inputs(data.commercial))
    return CalculationPreviewRead.model_validate(combined, from_attributes=True)


@router.get("/", response_model=CalculationListResponse)
async def list_calculations(
    calculation_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_READ),
) -> CalculationListResponse:
    page = await calculation_service.list_calculations(db, status=calculation_status, limit=limit, offset=offset)
    return CalculationListResponse(
        items=[_detail(item) for item in page.rows], total=page.total, limit=page.limit, offset=page.offset
    )


@router.post("/", response_model=CalculationDetail, status_code=status.HTTP_201_CREATED)
async def create_calculation(
    data: CalculationCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_UPDATE),
) -> CalculationDetail:
    try:
        calculation = await calculation_service.create_calculation(db, data)
        await db.commit()
    except OrderDomainError as exc:
        await db.rollback()
        _raise_http(exc)
    return _detail(calculation)


@router.get("/{calculation_id}", response_model=CalculationDetail)
async def get_calculation(
    calculation_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_READ),
) -> CalculationDetail:
    try:
        return _detail(await calculation_service.get_calculation(db, calculation_id))
    except OrderDomainError as exc:
        _raise_http(exc)


@router.put("/{calculation_id}", response_model=CalculationDetail)
async def update_calculation(
    calculation_id: int,
    data: CalculationUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_UPDATE),
) -> CalculationDetail:
    try:
        calculation = await calculation_service.update_calculation(db, calculation_id, data)
        await db.commit()
    except OrderDomainError as exc:
        await db.rollback()
        _raise_http(exc)
    return _detail(calculation)


@router.post("/{calculation_id}/approve", response_model=CalculationRevisionRead)
async def approve_calculation(
    calculation_id: int,
    data: CalculationApprove,
    db: AsyncSession = Depends(get_db),
    user: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_APPROVE),
) -> CalculationRevisionRead:
    try:
        revision = await calculation_service.approve_calculation(
            db, calculation_id, data.expected_version, data.warning_reasons, user.id if user else None
        )
        await db.commit()
        await db.refresh(revision)
    except OrderDomainError as exc:
        await db.rollback()
        _raise_http(exc)
    return CalculationRevisionRead.model_validate(revision)


@router.get("/{calculation_id}/revisions", response_model=list[CalculationRevisionRead])
async def list_calculation_revisions(
    calculation_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_READ),
) -> list[CalculationRevisionRead]:
    try:
        calculation = await calculation_service.get_calculation(db, calculation_id)
    except OrderDomainError as exc:
        _raise_http(exc)
    return [
        CalculationRevisionRead.model_validate(revision)
        for revision in sorted(calculation.revisions, key=lambda item: item.revision_number, reverse=True)
    ]


@router.post("/{calculation_id}/archive", response_model=CalculationDetail)
async def archive_calculation(
    calculation_id: int,
    expected_version: int = Query(gt=0),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_APPROVE),
) -> CalculationDetail:
    try:
        calculation = await calculation_service.archive_calculation(db, calculation_id, expected_version)
        await db.commit()
    except OrderDomainError as exc:
        await db.rollback()
        _raise_http(exc)
    return _detail(calculation)


@router.post("/{calculation_id}/templates", response_model=CalculationTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    calculation_id: int,
    data: CalculationTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_UPDATE),
) -> CalculationTemplateRead:
    try:
        template = await calculation_service.create_template(db, calculation_id, data.name)
        await db.commit()
        await db.refresh(template)
    except OrderDomainError as exc:
        await db.rollback()
        _raise_http(exc)
    return CalculationTemplateRead.model_validate(template)
