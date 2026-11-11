"""Hashable live machine metadata for status push deduplication."""


def machine_status_key(state) -> tuple:
    return (
        tuple((n.nozzle_type, n.nozzle_diameter) for n in getattr(state, "nozzles", None) or []),
        repr(getattr(state, "nozzle_rack", None)),
        getattr(state, "firmware_version", None),
        getattr(state, "developer_mode", None),
        tuple(getattr(state, "print_ams_mapping", None) or []),
        getattr(state, "airduct_mode", None),
        getattr(state, "left_aux_fan_speed", None),
        getattr(state, "exhaust_fan_present", None),
        repr(getattr(state, "h2d_extruder_snow", None)),
    )
