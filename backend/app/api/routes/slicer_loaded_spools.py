"""Read the live feed slots available to the slicer dialog."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import OwnershipAccess, require_permission_with_key
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import resolve_row_visibility
from backend.app.models.printer import Printer
from backend.app.models.slot_preset import SlotPresetMapping
from backend.app.schemas.slicer_presets import (
    LoadedSpoolPreset,
    LoadedSpoolPrinter,
    LoadedSpoolsResponse,
    LoadedSpoolTray,
    LoadedSpoolUnit,
)
from backend.app.services.ams_slot_presence import spool_present
from backend.app.services.printer_manager import printer_manager
from backend.app.utils.printer_models import normalize_printer_model, normalize_printer_model_id

router = APIRouter()


def _records(value: object) -> list[dict]:
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def _slot_id(value: object, default: int = -1) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 3:
        return int(value)
    return default


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _tray(raw: dict, ams_id: int, tray_id: int, presets: dict[tuple[int, int], LoadedSpoolPreset]) -> LoadedSpoolTray:
    exists = spool_present(raw)
    state = _slot_id(raw.get("state"))
    material = _text(raw.get("tray_type"))
    return LoadedSpoolTray(
        ams_id=ams_id,
        tray_id=tray_id,
        tray_type=material,
        tray_sub_brands=_text(raw.get("tray_sub_brands")),
        tray_color=_text(raw.get("tray_color")),
        tray_info_idx=_text(raw.get("tray_info_idx")),
        exists=exists,
        state=state if state >= 0 else None,
        saved_preset=presets.get((ams_id, tray_id)) if exists is not False and material else None,
    )


def _printer(printer: Printer, raw: dict, presets: dict[tuple[int, int], LoadedSpoolPreset]) -> LoadedSpoolPrinter:
    units = []
    ams = raw.get("ams")
    for unit in _records(ams.get("ams") if isinstance(ams, dict) else ams):
        ams_id = _slot_id(unit.get("id"))
        if not (0 <= ams_id < 16 or 128 <= ams_id <= 135):
            continue
        trays = []
        for entry in _records(unit.get("tray")):
            tray_id = _slot_id(entry.get("id"))
            if 0 <= tray_id < 4:
                trays.append(_tray(entry, ams_id, tray_id, presets))
        units.append(LoadedSpoolUnit(id=ams_id, trays=trays))

    holders = {}
    for entry in _records(raw.get("vt_tray")):
        holder = _slot_id(entry.get("id"), default=254 if "id" not in entry else -1)
        if holder in (254, 255):
            holders[holder - 254] = _tray(entry, 255, holder - 254, presets)
    return LoadedSpoolPrinter(
        id=printer.id,
        name=printer.name,
        model=normalize_printer_model_id(printer.model) or normalize_printer_model(printer.model),
        ams=units,
        external=list(holders.values()),
        external_holders=max(holders, default=-1) + 1,
    )


@router.get("/loaded-spools", response_model=LoadedSpoolsResponse)
async def list_loaded_spools(
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.PRINTERS_READ)),
) -> LoadedSpoolsResponse:
    """Read live slots for active printers in the caller's printer scope."""
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    if not (
        visibility.has_permission(Permission.PRINTERS_READ) and visibility.has_permission(Permission.LIBRARY_UPLOAD)
    ):
        raise HTTPException(403, "Printer read and library upload permissions are required")

    query = select(Printer).where(Printer.is_active.is_(True)).order_by(Printer.name, Printer.id)
    if (scope := visibility.printer_ids) is not None:
        query = query.where(Printer.id.in_(scope))
    connected = {}
    for printer in (await db.scalars(query)).all():
        status = printer_manager.get_status(printer.id)
        if status is not None and status.connected:
            connected[printer.id] = (printer, status.raw_data or {})
    if not connected:
        return LoadedSpoolsResponse()

    mappings = await db.scalars(select(SlotPresetMapping).where(SlotPresetMapping.printer_id.in_(connected)))
    by_printer: dict[int, dict[tuple[int, int], LoadedSpoolPreset]] = {}
    for mapping in mappings:
        by_printer.setdefault(mapping.printer_id, {})[mapping.ams_id, mapping.tray_id] = LoadedSpoolPreset(
            preset_id=mapping.preset_id,
            preset_name=mapping.preset_name,
            preset_source=mapping.preset_source,
            tray_info_idx=mapping.tray_info_idx,
        )
    return LoadedSpoolsResponse(
        printers=[_printer(printer, raw, by_printer.get(printer.id, {})) for printer, raw in connected.values()]
    )
