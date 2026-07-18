from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.config import settings as app_settings
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.calculation import Calculation
from backend.app.models.calculation_project import CalculationProjectFile, CalculationProjectPlate
from backend.app.models.user import User
from backend.app.schemas.calculation_project import CalculationProjectFileRead, CalculationProjectPlateRead
from backend.app.services.calculation_project import InvalidProjectFile, analyze_project_file

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
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_READ),
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
