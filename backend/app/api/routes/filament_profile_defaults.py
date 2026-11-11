"""Manage the product defaults that new spools inherit."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import OwnershipAccess, require_permission_with_key
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.models.filament_profile_default import FilamentProfileDefault
from backend.app.models.printer import Printer
from backend.app.models.spool import Spool
from backend.app.schemas.filament_profile_default import FilamentProfileWrite
from backend.app.services.filament_profile_defaults import (
    calibration_key,
    copy_profiles,
    matching_defaults,
    product_key,
    profile_product,
)

router = APIRouter(prefix="/profile-defaults")


def _profiles_visible(row, access):
    return all(access.allows_printer(item["printer_id"]) for item in row.k_profiles)


def _serialize(row, access):
    return {
        **profile_product(row).model_dump(),
        "id": row.id,
        "slicer_filament": row.slicer_filament,
        "slicer_filament_name": row.slicer_filament_name,
        "presets": row.presets,
        "k_profiles": [item for item in row.k_profiles if access.allows_printer(item["printer_id"])],
        "can_edit": _profiles_visible(row, access),
    }


@router.get("/")
async def list_filament_profile_defaults(
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.INVENTORY_READ)),
):
    rows = await db.scalars(
        select(FilamentProfileDefault).order_by(FilamentProfileDefault.material, FilamentProfileDefault.id)
    )
    return [_serialize(row, access) for row in rows]


@router.put("/")
async def save_filament_profile_default(
    body: FilamentProfileWrite,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.INVENTORY_UPDATE)),
):
    printer_ids = {row.printer_id for row in body.k_profiles}
    if any(not access.allows_printer(printer_id) for printer_id in printer_ids):
        raise HTTPException(404, "Printer not found")
    if printer_ids and set(await db.scalars(select(Printer.id).where(Printer.id.in_(printer_ids)))) != printer_ids:
        raise HTTPException(404, "Printer not found")
    if len({row.printer_model for row in body.presets}) != len(body.presets):
        raise HTTPException(422, "Each printer model can have only one preset")
    if len({calibration_key(row) for row in body.k_profiles}) != len(body.k_profiles):
        raise HTTPException(422, "Calibration contexts must be unique")
    key = product_key(body)
    row = await db.scalar(
        select(FilamentProfileDefault).where(FilamentProfileDefault.product_key == key).with_for_update()
    )
    if row is not None and not _profiles_visible(row, access):
        raise HTTPException(404, "Profile default not found")
    if row is None:
        row = FilamentProfileDefault(product_key=key)
        db.add(row)
    for name, value in body.model_dump().items():
        setattr(row, name, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "The product default changed. Reload and retry.") from exc
    await db.refresh(row)
    return _serialize(row, access)


@router.delete("/{default_id}")
async def delete_filament_profile_default(
    default_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.INVENTORY_UPDATE)),
):
    row = await db.get(FilamentProfileDefault, default_id, with_for_update=True)
    if row is None or not _profiles_visible(row, access):
        raise HTTPException(404, "Profile default not found")
    await db.delete(row)
    await db.commit()
    return {"status": "deleted"}


@router.post("/{default_id}/apply")
async def apply_filament_profile_default(
    default_id: int,
    spoolman: bool = Query(False),
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.INVENTORY_UPDATE)),
):
    row = await db.get(FilamentProfileDefault, default_id)
    if row is None or not _profiles_visible(row, access):
        raise HTTPException(404, "Profile default not found")
    client = None
    if spoolman:
        from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool
        from backend.app.api.routes.spoolman_inventory import _get_client, _translate_spoolman_errors

        client = await _get_client(db)
        async with _translate_spoolman_errors():
            spools = [_map_spoolman_spool(spool) for spool in await client.get_all_spools()]
    else:
        spools = list(await db.scalars(select(Spool).where(Spool.archived_at.is_(None))))
    applied, failed = 0, 0
    for spool in spools:
        if product_key(spool, all_colors=not row.color_name) != row.product_key:
            continue
        try:
            async with db.begin_nested():
                # Use the same general and colour-specific precedence as a new spool.
                rows = await matching_defaults(db, spool)
                applied += int(await copy_profiles(db, spool, rows, access.printer_ids, client=client))
        except Exception:
            if client is None:
                raise
            failed += 1
    await db.commit()
    return {"applied": applied, "failed": failed}
