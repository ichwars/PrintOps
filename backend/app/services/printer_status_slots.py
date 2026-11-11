"""Public feed occupancy from the existing per-nozzle snow evidence."""


def extruder_slots(state) -> dict:
    snow = getattr(state, "h2d_extruder_snow", None)
    if not isinstance(snow, dict):
        return {}
    result = {}
    for extruder, tray in snow.items():
        if type(extruder) is not int or extruder not in (0, 1) or type(tray) is not int:
            continue
        if 0 <= tray < 128:
            unit = tray // 4
        elif 128 <= tray <= 135:
            unit = tray
        elif tray in (254, 255):
            unit = None
        else:
            continue
        result[str(extruder)] = {"ams_id": unit, "has_filament": tray != 255}
    return result


def backup_trays(mapping: list, changes: list, *, second_external_holder: bool) -> dict[int, int]:
    """Follow tray changes outside the original print mapping back to a mapped feed."""
    allowed = {*range(64), *range(128, 136), 254}
    if second_external_holder:
        allowed.add(255)
    mapped = {tray for tray in mapping if type(tray) is int and tray in allowed}
    if not mapped:
        return {}

    owners: dict[int, int] = {}
    backups: dict[int, int] = {}
    original = None
    for change in changes:
        if not isinstance(change, (list, tuple)) or not change:
            continue
        tray = change[0]
        if type(tray) is not int or tray not in allowed:
            continue
        if tray in mapped:
            original = tray
            backups.pop(original, None)
            continue
        original = owners.get(tray, original)
        if original is not None:
            owners[tray] = original
            backups[original] = tray
    return backups
