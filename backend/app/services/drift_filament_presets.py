"""Load a remote spool's fallback preset before opening the drift writer's DB session."""

import logging

from sqlalchemy import select

from backend.app.models.spoolman_k_profile import SpoolmanKProfile
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.calibration_context import resolve_spool_calibration
from backend.app.services.inventory_mode import spoolman_owns_assignments
from backend.app.services.printer_manager import printer_manager
from backend.app.services.spool_filament_presets import resolve_spool_preset
from backend.app.utils.filament_ids import normalize_slicer_filament

logger = logging.getLogger(__name__)


def _wire_preset(value) -> str:
    preset = normalize_slicer_filament(value)[0] or ""
    if preset.startswith("GF") or (preset.startswith("P") and not preset.startswith(("PFUS", "PFCN"))):
        return preset
    return ""


async def spoolman_drift_preset_hints(printer_id: int, state, slots: set[tuple[int, int]]) -> dict[tuple, str]:
    """Return hints bound to the original assignment row and spool ID.

    Current calibration identities have priority. Read the remote legacy value
    only when no local model override applies, including an intentionally blank
    override. Network failures retain the existing live-tray fallback.
    """
    from backend.app.core.database import async_session

    hints: dict[tuple, str] = {}
    remote: dict[int, list[tuple]] = {}
    if not slots:
        return hints
    async with async_session() as db:
        if not await spoolman_owns_assignments(db):
            return hints
        rows = (
            await db.scalars(
                select(SpoolmanSlotAssignment).where(
                    SpoolmanSlotAssignment.printer_id == printer_id,
                )
            )
        ).all()
        for row in rows:
            if (row.ams_id, row.tray_id) not in slots:
                continue
            profiles = (
                await db.scalars(
                    select(SpoolmanKProfile).where(
                        SpoolmanKProfile.spoolman_spool_id == row.spoolman_spool_id,
                    )
                )
            ).all()
            context, stored, live = resolve_spool_calibration(
                profiles,
                state,
                printer_manager.get_model(printer_id),
                printer_id,
                row.ams_id,
                row.tray_id,
            )
            if context is None or stored is None or stored.cali_idx is None or stored.cali_idx < 0:
                continue
            if (live and live.filament_id) or stored.setting_id:
                continue
            key = (row.id, row.spoolman_spool_id)
            preset = await resolve_spool_preset(db, {"id": row.spoolman_spool_id}, printer_id, spoolman=True)
            if preset.configured:
                hints[key] = _wire_preset(preset.slicer_filament)
            else:
                remote.setdefault(row.spoolman_spool_id, []).append(key)
    # The local read session is closed before any HTTP request.
    if remote:
        from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool
        from backend.app.services.spoolman import get_spoolman_client

        client = await get_spoolman_client()
        if client:
            for spool_id, keys in remote.items():
                try:
                    mapped = _map_spoolman_spool(await client.get_spool(spool_id))
                    preset = _wire_preset(mapped.get("slicer_filament"))
                except Exception as exc:
                    logger.debug("Could not read the fallback preset for Spoolman spool %s: %s", spool_id, exc)
                    continue
                hints.update(dict.fromkeys(keys, preset))
    return hints
