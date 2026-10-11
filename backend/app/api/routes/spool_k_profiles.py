import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.spool import Spool
from backend.app.models.spool_k_profile import SpoolKProfile
from backend.app.models.spoolman_k_profile import SpoolmanKProfile
from backend.app.models.user import User
from backend.app.schemas.spool import SpoolKProfileBase, SpoolKProfileResponse
from backend.app.utils.calibration_values import diameter, flow_type


def validate_contexts(profiles):
    for profile in profiles:
        size = diameter(profile.nozzle_diameter)
        if size is None or profile.extruder not in (0, 1):
            raise HTTPException(422, "An explicit diameter and supported extruder are required")
        profile.nozzle_diameter = size
    keys = {(p.printer_id, p.extruder, p.nozzle_diameter, flow_type(p.nozzle_type)) for p in profiles}
    if len(keys) != len(profiles):
        raise HTTPException(422, "Only one K-profile per printer, extruder, diameter and reported flow is allowed")


router = APIRouter()

# ── K-Profiles ───────────────────────────────────────────────────────────────


@router.get("/spools/{spool_id}/k-profiles", response_model=list[SpoolKProfileResponse])
async def list_k_profiles(
    spool_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    """List K-profiles for a spool."""
    result = await db.execute(select(SpoolKProfile).where(SpoolKProfile.spool_id == spool_id))
    return list(result.scalars().all())


@router.put("/spools/{spool_id}/k-profiles", response_model=list[SpoolKProfileResponse])
async def replace_k_profiles(
    spool_id: int,
    profiles: list[SpoolKProfileBase],
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    """Replace all K-profiles for a spool (batch save)."""
    validate_contexts(profiles)
    # Verify spool exists
    result = await db.execute(select(Spool).where(Spool.id == spool_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Spool not found")

    await db.execute(delete(SpoolKProfile).where(SpoolKProfile.spool_id == spool_id))

    # Create new
    new_profiles = []
    for p in profiles:
        kp = SpoolKProfile(spool_id=spool_id, **p.model_dump())
        db.add(kp)
        new_profiles.append(kp)

    await db.commit()
    for kp in new_profiles:
        await db.refresh(kp)
    return new_profiles


spoolman_router = APIRouter()
logger = logging.getLogger(__name__)


@spoolman_router.get("/spools/{spool_id}/k-profiles")
async def get_spoolman_k_profiles(
    spool_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> list[dict]:
    """Return all local K-value calibration profiles for a Spoolman spool."""
    from backend.app.api.routes.spoolman_inventory import _get_client, _k_profile_to_dict

    await _get_client(db)
    result = await db.execute(select(SpoolmanKProfile).where(SpoolmanKProfile.spoolman_spool_id == spool_id))
    profiles = result.scalars().all()
    return [_k_profile_to_dict(p) for p in profiles]


@spoolman_router.put("/spools/{spool_id}/k-profiles")
async def save_spoolman_k_profiles(
    spool_id: int = Path(..., gt=0),
    profiles: list[SpoolKProfileBase] = Body(...),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
) -> list[dict]:
    """Replace all K-value calibration profiles for a Spoolman spool."""
    from backend.app.api.routes.spoolman_inventory import _get_client, _k_profile_to_dict, _translate_spoolman_errors

    validate_contexts(profiles)
    client = await _get_client(db)
    async with _translate_spoolman_errors():
        await client.get_spool(spool_id)

    saved: list[SpoolmanKProfile] = []
    try:
        await db.execute(delete(SpoolmanKProfile).where(SpoolmanKProfile.spoolman_spool_id == spool_id))
        for profile in profiles:
            obj = SpoolmanKProfile(
                spoolman_spool_id=spool_id,
                printer_id=profile.printer_id,
                extruder=profile.extruder,
                nozzle_diameter=profile.nozzle_diameter,
                nozzle_type=profile.nozzle_type,
                k_value=profile.k_value,
                name=profile.name,
                cali_idx=profile.cali_idx,
                setting_id=profile.setting_id,
            )
            db.add(obj)
            saved.append(obj)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(422, "Duplicate or invalid K-profile (check printer_id and nozzle uniqueness)") from exc
    except Exception as exc:
        await db.rollback()
        logger.error("K-profile save for spool %d failed: %s", spool_id, exc)
        raise HTTPException(500, "Failed to save K-profiles") from exc

    for obj in saved:
        await db.refresh(obj)

    return [_k_profile_to_dict(p) for p in saved]
