from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.routes.settings import get_setting
from backend.app.core.auth import RequireCameraStreamTokenIfAuthEnabled, RequirePermissionIfAuthEnabled
from backend.app.core.config import settings as app_settings
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.calculation import Calculation
from backend.app.models.calculation_project import CalculationProjectFile, CalculationProjectPlate
from backend.app.models.calculation_slice import CalculationSliceResult
from backend.app.models.user import User
from backend.app.schemas.calculation_project import (
    CalculationProjectFileRead,
    CalculationProjectPlateRead,
    CalculationSliceRequest,
)
from backend.app.services.calculation_estimator import BoundsMm, EstimatorSettings, PlateGeometry, estimate_plate
from backend.app.services.calculation_project import InvalidProjectFile, analyze_project_file
from backend.app.services.calculation_slicing import build_cache_key
from backend.app.services.slicer_api import SlicerApiError, SlicerApiService

router = APIRouter(prefix="/calculations", tags=["calculation-project-files"])


def _storage_root(calculation_id: int) -> Path:
    root = Path(app_settings.base_dir) / "calculations" / str(calculation_id) / "sources"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _plate_read(file_id: int, plate: CalculationProjectPlate) -> CalculationProjectPlateRead:
    return CalculationProjectPlateRead(
        id=plate.id,
        plate_index=plate.plate_index,
        stable_key=plate.stable_key,
        name=plate.name,
        object_count=plate.object_count,
        detected_materials=plate.detected_materials,
        detected_grams=plate.detected_grams,
        detected_hours=plate.detected_hours,
        geometry=plate.geometry,
        thumbnail_url=(
            f"/api/v1/calculations/project-files/{file_id}/plates/{plate.id}/thumbnail"
            if plate.thumbnail_path
            else None
        ),
    )


def _file_read(project_file: CalculationProjectFile) -> CalculationProjectFileRead:
    return CalculationProjectFileRead(
        id=project_file.id,
        calculation_id=project_file.calculation_id,
        revision_number=project_file.revision_number,
        original_filename=project_file.original_filename,
        sha256=project_file.sha256,
        size_bytes=project_file.size_bytes,
        analysis_status=project_file.analysis_status,
        analysis_error=project_file.analysis_error,
        printer_metadata=project_file.printer_metadata,
        created_at=project_file.created_at,
        plates=[_plate_read(project_file.id, plate) for plate in project_file.plates],
    )


@router.post("/{calculation_id}/project-files", response_model=CalculationProjectFileRead, status_code=201)
async def upload_project_file(
    calculation_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_UPDATE),
) -> CalculationProjectFileRead:
    calculation = await db.get(Calculation, calculation_id)
    if calculation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Kalkulation fehlt"})
    if not (file.filename or "").lower().endswith(".3mf"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_project_file", "message": "Nur 3MF-Projektdateien sind zulässig"},
        )
    payload = await file.read()
    digest = hashlib.sha256(payload).hexdigest()
    revision = (
        int(
            await db.scalar(
                select(func.coalesce(func.max(CalculationProjectFile.revision_number), 0)).where(
                    CalculationProjectFile.calculation_id == calculation_id
                )
            )
        )
        + 1
    )
    root = _storage_root(calculation_id)
    target = root / f"{digest}-r{revision}.3mf"
    temporary = root / f".{digest}-r{revision}.tmp"
    temporary.write_bytes(payload)
    temporary.replace(target)
    try:
        analysis = analyze_project_file(target)
    except InvalidProjectFile as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "analysis_failed", "message": str(exc)},
        ) from exc

    project_file = CalculationProjectFile(
        calculation_id=calculation_id,
        revision_number=revision,
        original_filename=(file.filename or "project.3mf")[:255],
        stored_path=str(target.relative_to(Path(app_settings.base_dir))),
        sha256=digest,
        size_bytes=len(payload),
        analysis_status="completed",
        printer_metadata=analysis.printer_metadata,
    )
    db.add(project_file)
    await db.flush()
    thumbnail_root = root / "thumbnails"
    thumbnail_root.mkdir(exist_ok=True)
    for analyzed in analysis.plates:
        plate = CalculationProjectPlate(
            project_file_id=project_file.id,
            plate_index=analyzed.plate_index,
            stable_key=analyzed.stable_key,
            name=analyzed.name,
            object_count=analyzed.object_count,
            detected_materials=list(analyzed.detected_materials),
            detected_grams=analyzed.detected_grams,
            detected_hours=analyzed.detected_hours,
            geometry={
                "triangle_count": analyzed.geometry.triangle_count,
                "volume_cm3": str(analyzed.geometry.volume_cm3),
                "bounds_mm": {
                    "width": str(analyzed.geometry.bounds_mm.width),
                    "depth": str(analyzed.geometry.bounds_mm.depth),
                    "height": str(analyzed.geometry.bounds_mm.height),
                },
            },
        )
        db.add(plate)
        await db.flush()
        if analyzed.thumbnail_bytes:
            thumbnail = thumbnail_root / f"{project_file.id}-{analyzed.plate_index}.png"
            thumbnail.write_bytes(analyzed.thumbnail_bytes)
            plate.thumbnail_path = str(thumbnail.relative_to(Path(app_settings.base_dir)))
    await db.commit()
    loaded = await _load_file(db, project_file.id)
    return _file_read(loaded)


async def _load_file(db: AsyncSession, file_id: int) -> CalculationProjectFile:
    project_file = await db.scalar(
        select(CalculationProjectFile)
        .where(CalculationProjectFile.id == file_id)
        .options(selectinload(CalculationProjectFile.plates))
    )
    if project_file is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Projektdatei fehlt"})
    return project_file


@router.get("/{calculation_id}/project-files", response_model=list[CalculationProjectFileRead])
async def list_project_files(
    calculation_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_READ),
) -> list[CalculationProjectFileRead]:
    files = list(
        await db.scalars(
            select(CalculationProjectFile)
            .where(CalculationProjectFile.calculation_id == calculation_id)
            .options(selectinload(CalculationProjectFile.plates))
            .order_by(CalculationProjectFile.revision_number)
        )
    )
    return [_file_read(project_file) for project_file in files]


@router.get("/project-files/{file_id}/plates/{plate_id}/thumbnail")
async def get_project_plate_thumbnail(
    file_id: int,
    plate_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = RequireCameraStreamTokenIfAuthEnabled,
):
    plate = await db.scalar(
        select(CalculationProjectPlate).where(
            CalculationProjectPlate.id == plate_id,
            CalculationProjectPlate.project_file_id == file_id,
        )
    )
    if plate is None or not plate.thumbnail_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Vorschau fehlt"})
    base = Path(app_settings.base_dir).resolve()
    target = (base / plate.thumbnail_path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Vorschau fehlt"})
    return FileResponse(target, media_type="image/png")


@router.post("/project-files/{file_id}/slice")
async def slice_project_plates(
    file_id: int,
    request: CalculationSliceRequest,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_UPDATE),
):
    project_file = await _load_file(db, file_id)
    selected = [plate for plate in project_file.plates if plate.id in set(request.plate_ids)]
    if len(selected) != len(set(request.plate_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "plate_not_found", "message": "Platte fehlt"})
    preferred = (await get_setting(db, "preferred_slicer")) or "bambu_studio"
    if preferred == "orcaslicer":
        configured = await get_setting(db, "orcaslicer_api_url")
        api_url = (configured or app_settings.slicer_api_url).strip()
    else:
        configured = await get_setting(db, "bambu_studio_api_url")
        api_url = (configured or app_settings.bambu_studio_api_url).strip()
    source = (Path(app_settings.base_dir) / project_file.stored_path).resolve()
    model_bytes = source.read_bytes()
    results = []
    for plate in selected:
        profile_snapshot = {
            "slicer": preferred,
            "mode": "embedded",
            "printer": request.printer_preset,
            "process": request.process_preset,
            "filament": request.filament_preset,
        }
        key = build_cache_key(
            file_sha256=project_file.sha256,
            plate_index=plate.plate_index,
            profiles=profile_snapshot,
        )
        cached = await db.scalar(select(CalculationSliceResult).where(CalculationSliceResult.cache_key == key))
        if cached is not None:
            results.append(cached)
            continue
        try:
            async with SlicerApiService(api_url) as slicer:
                sliced = await slicer.slice_without_profiles(
                    model_bytes=model_bytes,
                    model_filename=project_file.original_filename,
                    plate=plate.plate_index,
                    export_3mf=False,
                )
            result = CalculationSliceResult(
                project_plate_id=plate.id,
                cache_key=key,
                status="completed",
                source="slicer",
                print_hours=Decimal(sliced.print_time_seconds) / Decimal("3600"),
                material_grams=Decimal(str(sliced.filament_used_g)),
                warnings=[],
                profile_snapshot=profile_snapshot,
            )
        except SlicerApiError as exc:
            if not request.allow_estimate_fallback:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, detail={"code": "slicing_failed", "message": str(exc)}
                ) from exc
            geometry_data = plate.geometry or {}
            bounds_data = geometry_data.get("bounds_mm") or {}
            estimate = estimate_plate(
                PlateGeometry(
                    object_count=plate.object_count,
                    triangle_count=int(geometry_data.get("triangle_count", 0)),
                    volume_cm3=Decimal(str(geometry_data.get("volume_cm3", 0))),
                    bounds_mm=BoundsMm(
                        Decimal(str(bounds_data.get("width", 0))),
                        Decimal(str(bounds_data.get("depth", 0))),
                        Decimal(str(bounds_data.get("height", 0))),
                    ),
                ),
                EstimatorSettings(None, Decimal("20"), Decimal("0.2"), Decimal("0.4"), Decimal("60"), 2),
                (plate.detected_materials[0].get("type") if plate.detected_materials else "PLA"),
            )
            result = CalculationSliceResult(
                project_plate_id=plate.id,
                cache_key=key,
                status="completed",
                source="estimate",
                print_hours=estimate.print_hours,
                material_grams=estimate.material_grams,
                fallback_reason=str(exc),
                warnings=list(estimate.warnings),
                profile_snapshot=profile_snapshot,
            )
        db.add(result)
        await db.flush()
        results.append(result)
    await db.commit()
    return [
        {
            "id": item.id,
            "project_plate_id": item.project_plate_id,
            "status": item.status,
            "source": item.source,
            "print_hours": str(item.print_hours) if item.print_hours is not None else None,
            "material_grams": str(item.material_grams) if item.material_grams is not None else None,
            "fallback_reason": item.fallback_reason,
            "warnings": item.warnings,
        }
        for item in results
    ]
