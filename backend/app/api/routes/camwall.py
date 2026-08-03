"""Read-only Cam Wall feed for token-authenticated kiosk displays."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequireCamWallTokenIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.models.printer import Printer
from backend.app.services.printer_manager import printer_manager

router = APIRouter(prefix="/camwall", tags=["camwall"])


@router.get("/printers")
async def list_camwall_printers(
    _: None = RequireCamWallTokenIfAuthEnabled,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return the minimal printer/status payload a passive wall display needs."""
    result = await db.execute(select(Printer).order_by(Printer.name))
    printers = list(result.scalars().all())

    payload: list[dict] = []
    for printer in printers:
        state = printer_manager.get_status(printer.id)
        entry: dict = {
            "id": printer.id,
            "name": printer.name,
            "camera_rotation": printer.camera_rotation or 0,
            "connected": bool(state and state.connected),
            "state": None,
            "progress": None,
            "remaining_time": None,
            "layer_num": None,
            "total_layers": None,
            "hms_errors": [],
        }
        if state is not None:
            entry.update(
                {
                    "state": state.state,
                    "progress": state.progress,
                    "remaining_time": state.remaining_time,
                    "layer_num": state.layer_num,
                    "total_layers": state.total_layers,
                    "hms_errors": [
                        {
                            "code": error.code,
                            "attr": error.attr,
                            "module": error.module,
                            "severity": error.severity,
                            "actions": error.actions or [],
                        }
                        for error in (state.hms_errors or [])
                    ],
                }
            )
        payload.append(entry)

    return payload
