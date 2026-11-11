"""AMS backup state with a trusted telemetry source per connection."""


def parse_ams_filament_backup_from_home_flag(home_flag: object) -> bool | None:
    """Old-protocol status uses bit10; booleans and malformed values are ignored."""
    return bool((home_flag >> 10) & 1) if type(home_flag) is int else None


def backup_value_from_status(client, data: dict) -> bool | None:
    """Prefer cfg permanently once seen; trust legacy deltas after a full status."""
    from backend.app.services.bambu_mqtt import parse_ams_filament_backup_from_cfg

    if data.get("command") not in (None, "push_status"):
        return None
    if "cfg" in data:
        client._backup_cfg_seen = True
        return parse_ams_filament_backup_from_cfg(data["cfg"])
    if getattr(client, "_backup_cfg_seen", False):
        return None
    if len(data) > 30:
        client._backup_home_flag_trusted = True
    if getattr(client, "_backup_home_flag_trusted", False):
        return parse_ams_filament_backup_from_home_flag(data.get("home_flag"))
    return None
