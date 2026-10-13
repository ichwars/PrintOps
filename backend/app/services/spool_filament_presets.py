"""Resolve model overrides identically for local, remote and RFID spools."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.printer import Printer
from backend.app.models.spool import Spool
from backend.app.models.spool_filament_preset import SpoolFilamentPreset, SpoolmanFilamentPreset
from backend.app.schemas.spool_filament_preset import known_printer_model
from backend.app.services.orca_filament_lookup import _ORCA_PROFILE_ID


@dataclass(frozen=True)
class ResolvedSpoolPreset:
    slicer_filament: str | None
    slicer_filament_name: str | None
    configured: bool = False


async def resolve_spool_preset(
    db: AsyncSession,
    spool: Spool | dict,
    printer_id: int,
    *,
    spoolman: bool = False,
) -> ResolvedSpoolPreset:
    """A model row wins, including NULL. Only an absent row inherits legacy.

    Use the persisted printer model so disconnected/reconnecting clients do
    not select a different preset. Unknown future models retain legacy behavior.
    """
    get = spool.get if isinstance(spool, dict) else lambda key: getattr(spool, key, None)
    legacy = ResolvedSpoolPreset(get("slicer_filament"), get("slicer_filament_name"))
    raw_model = await db.scalar(select(Printer.model).where(Printer.id == printer_id))
    model = known_printer_model(raw_model)
    if model is None:
        return legacy
    table = SpoolmanFilamentPreset if spoolman else SpoolFilamentPreset
    key = table.spoolman_spool_id if spoolman else table.spool_id
    row = await db.scalar(select(table).where(key == get("id"), table.printer_model == model))
    if row is None:
        return legacy
    return ResolvedSpoolPreset(row.slicer_filament, row.slicer_filament_name, True)


async def apply_spool_rfid_calibration(db, client, spool, state, model, printer_id, ams_id, tray_id, tray):
    """Keep firmware RFID metadata; use the selected preset for calibration only."""
    from backend.app.services.calibration_context import apply_rfid_calibration
    from backend.app.services.slicer_filament_resolver import resolve_slicer_filament
    from backend.app.utils.filament_types import generic_filament_id

    preset = await resolve_spool_preset(db, spool, printer_id)
    filament_id, _, _, _ = await resolve_slicer_filament(
        db=db,
        current_user=None,
        orca_generic_fallback=False,
        slicer_filament=preset.slicer_filament,
        slicer_filament_name=preset.slicer_filament_name,
        material=spool.material,
    )
    if not filament_id:
        filament_id = generic_filament_id(spool.material) if preset.configured else tray.get("tray_info_idx", "")
    if not filament_id and _ORCA_PROFILE_ID.fullmatch((preset.slicer_filament or "").removeprefix("orca_")):
        return
    apply_rfid_calibration(
        client, spool.k_profiles, state, model, printer_id, ams_id, tray_id, filament_id, tray.get("cali_idx")
    )


def _reported_tray(state, ams_id, tray_id):
    raw = getattr(state, "raw_data", None)
    if not isinstance(raw, dict):
        return None
    if ams_id == 255:
        trays = raw.get("vt_tray")
        trays = [trays] if isinstance(trays, dict) else trays
    else:
        ams = raw.get("ams")
        units = ams.get("ams") if isinstance(ams, dict) else ams
        if not isinstance(units, list):
            return None
        trays = []
        for unit in units:
            if not isinstance(unit, dict) or str(unit.get("id")) != str(ams_id):
                continue
            reported = unit.get("tray")
            if isinstance(reported, list):
                trays.extend(reported)
    if not isinstance(trays, list):
        return None
    return next((t for t in trays if isinstance(t, dict) and str(t.get("id")) == str(tray_id)), None)


async def reconcile_spoolman_rfid_slot(**slot):
    """Update the card and existing K selection without rewriting RFID metadata."""
    from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool
    from backend.app.models.spoolman_k_profile import SpoolmanKProfile
    from backend.app.services.calibration_context import apply_rfid_calibration
    from backend.app.services.printer_manager import printer_manager
    from backend.app.services.slicer_filament_resolver import resolve_slicer_filament
    from backend.app.services.slot_preset_writer import upsert_slot_preset_for_spoolman_spool
    from backend.app.utils.filament_types import generic_filament_id

    await upsert_slot_preset_for_spoolman_spool(**slot)
    db, printer_id = slot["db"], slot["printer_id"]
    state, client = printer_manager.get_status(printer_id), printer_manager.get_client(printer_id)
    if state is None or client is None:
        return
    tray = _reported_tray(state, slot["ams_id"], slot["tray_id"])
    if tray is None or "cali_idx" not in tray:
        return
    spool = _map_spoolman_spool(slot["spoolman_spool"])
    preset = await resolve_spool_preset(db, spool, printer_id, spoolman=True)
    filament_id, _, _, _ = await resolve_slicer_filament(
        db=db,
        current_user=None,
        orca_generic_fallback=False,
        slicer_filament=preset.slicer_filament,
        slicer_filament_name=preset.slicer_filament_name,
        material=spool.get("material"),
    )
    filament_id = filament_id or (
        generic_filament_id(spool.get("material")) if preset.configured else tray.get("tray_info_idx", "")
    )
    if not filament_id and _ORCA_PROFILE_ID.fullmatch((preset.slicer_filament or "").removeprefix("orca_")):
        return
    profiles = await db.scalars(select(SpoolmanKProfile).where(SpoolmanKProfile.spoolman_spool_id == spool["id"]))
    apply_rfid_calibration(
        client,
        list(profiles.all()),
        state,
        printer_manager.get_model(printer_id),
        printer_id,
        slot["ams_id"],
        slot["tray_id"],
        filament_id,
        tray["cali_idx"],
    )
