"""Local preset metadata only; inventory permissions apply in either mode."""

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.core.websocket import ws_manager
from backend.app.models.spool import Spool
from backend.app.models.spool_filament_preset import SpoolFilamentPreset, SpoolmanFilamentPreset
from backend.app.models.user import User
from backend.app.schemas.spool_filament_preset import SpoolFilamentPresetInput


def preset_router(*, spoolman: bool = False) -> APIRouter:
    router = APIRouter()
    table = SpoolmanFilamentPreset if spoolman else SpoolFilamentPreset
    key = table.spoolman_spool_id if spoolman else table.spool_id

    async def require_spool(db, spool_id):
        if spoolman:
            from backend.app.api.routes.spoolman_inventory import _get_client, _translate_spoolman_errors

            client = await _get_client(db)
            async with _translate_spoolman_errors():
                await client.get_spool(spool_id)
        elif await db.get(Spool, spool_id) is None:
            raise HTTPException(404, "Spool not found")

    @router.get("/spools/{spool_id}/filament-presets", response_model=list[SpoolFilamentPresetInput])
    async def list_presets(
        spool_id: int = Path(gt=0),
        db: AsyncSession = Depends(get_db),
        _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
    ):
        await require_spool(db, spool_id)
        rows = await db.scalars(select(table).where(key == spool_id).order_by(table.printer_model))
        return list(rows.all())

    @router.put("/spools/{spool_id}/filament-presets", response_model=list[SpoolFilamentPresetInput])
    async def replace_presets(
        presets: list[SpoolFilamentPresetInput],
        spool_id: int = Path(gt=0),
        db: AsyncSession = Depends(get_db),
        _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
    ):
        if len(presets) != len({p.printer_model for p in presets}):
            raise HTTPException(422, "Only one preset override per printer model is allowed")
        await require_spool(db, spool_id)
        try:
            await db.execute(delete(table).where(key == spool_id))
            field = "spoolman_spool_id" if spoolman else "spool_id"
            db.add_all([table(**{field: spool_id}, **p.model_dump()) for p in presets])
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(409, "Preset overrides changed concurrently; retry the save") from exc
        await ws_manager.broadcast({"type": "inventory_changed"})
        return sorted(presets, key=lambda p: p.printer_model)

    return router
