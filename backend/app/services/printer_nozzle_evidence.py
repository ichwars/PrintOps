"""Live nozzle presence for filament routing, separate from calibration authority."""


def reports_two_nozzles(state) -> bool:
    raw = getattr(state, "raw_data", None) or {}
    nozzles = getattr(state, "nozzles", None)
    nozzles = nozzles if isinstance(nozzles, (list, tuple)) else []
    wiring = getattr(state, "ams_extruder_map", None)
    external = raw.get("vt_tray")
    return bool(
        (len(nozzles) > 1 and getattr(nozzles[1], "nozzle_diameter", ""))
        or raw.get("ams_extruder_map")
        or (isinstance(wiring, dict) and wiring)
        or (isinstance(external, list) and len(external) > 1)
    )
