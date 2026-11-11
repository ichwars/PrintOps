"""Decode options from the slicer's project_file command for queue intake."""

import json

from backend.app.services.bambu_mqtt import resolve_external_spools_in_mapping

_WORKFLOW_FIELDS = (
    ("bed_leveling", "bed_levelling", "auto_bed_leveling"),
    ("flow_cali", "flow_cali", "extrude_cali_flag"),
    ("vibration_cali", "vibration_cali", None),
    ("layer_inspect", "layer_inspect", None),
    ("timelapse", "timelapse", None),
    ("nozzle_offset_cali", "nozzle_offset_cali", None),
)


def _boolean_option(value):
    if type(value) in (bool, int) and value in (0, 1):
        return bool(value)
    return None


def _decode_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, list) and value else None


def queue_options(data, *, bound, keep_ams, keep_nozzle, dual_nozzle):
    options = {}
    for field, column, companion in _WORKFLOW_FIELDS:
        value = (
            _boolean_option(data.get(companion))
            if companion and companion in data
            else _boolean_option(data.get(field))
        )
        if value is not None:
            options[column] = value
    if bound and (use_ams := _boolean_option(data.get("use_ams"))) is not None:
        options["use_ams"] = use_ams
    if keep_nozzle:
        nozzle = _decode_list(data.get("nozzle_mapping"))
        if nozzle and all(type(item) is int for item in nozzle):
            options["nozzle_mapping"] = json.dumps(nozzle)
    if keep_ams:
        flat = _decode_list(data.get("ams_mapping"))
        if flat and all(type(item) is int and -1 <= item <= 255 for item in flat):
            mapping = resolve_external_spools_in_mapping(flat, _decode_list(data.get("ams_mapping2")), dual_nozzle)
            if all(type(item) is int for item in mapping) and any(item >= 0 for item in mapping):
                options["ams_mapping"] = json.dumps(mapping)
    return options


def mapping_reaches_plate(mapping, slots):
    return all(1 <= slot <= len(mapping) and mapping[slot - 1] >= 0 for slot in slots)
