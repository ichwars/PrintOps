"""Read physical and external spool slots from printer status."""

from __future__ import annotations

from backend.app.utils.tray_ids import external_tray_id


def _live_slot_tray(state, ams_id: int, tray_id: int) -> dict:
    """The tray the printer reports for a slot right now, or {} (external: vt_tray 254/255)."""
    raw = getattr(state, "raw_data", None) if state is not None else None
    if not isinstance(raw, dict):
        return {}
    if ams_id == 255:
        vt_trays = raw.get("vt_tray") or []
        for vt in [vt_trays] if isinstance(vt_trays, dict) else vt_trays:
            if isinstance(vt, dict) and str(vt.get("id", 254)) == str(external_tray_id(tray_id)):
                return vt
        return {}
    units = raw.get("ams") or []
    if isinstance(units, dict):
        units = units.get("ams") or []
    for unit in units if isinstance(units, list) else []:
        if isinstance(unit, dict) and str(unit.get("id")) == str(ams_id):
            for tray in unit.get("tray") or []:
                if isinstance(tray, dict) and str(tray.get("id")) == str(tray_id):
                    return tray
    return {}
