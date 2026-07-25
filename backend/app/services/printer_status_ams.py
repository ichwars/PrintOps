from __future__ import annotations

from typing import Any

from backend.app.schemas.printer import AMSTray, AMSUnit


def _sanitize_tag_uid(value: Any) -> str | None:
    tag_uid = str(value or "")
    return None if tag_uid in ("", "0000000000000000") else tag_uid


def _sanitize_tray_uuid(value: Any) -> str | None:
    tray_uuid = str(value or "")
    return None if tray_uuid in ("", "00000000000000000000000000000000") else tray_uuid


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_kprofile_map(kprofiles: list[Any] | None) -> dict[int, float]:
    """Map calibration profile slot ids to K values for AMS tray display."""
    kprofile_map: dict[int, float] = {}
    for kp in kprofiles or []:
        if kp.slot_id is not None and kp.k_value:
            try:
                kprofile_map[kp.slot_id] = float(kp.k_value)
            except (ValueError, TypeError):
                pass
    return kprofile_map


def _tray_k_value(tray_data: dict[str, Any], kprofile_map: dict[int, float]) -> tuple[Any, Any]:
    k_value = tray_data.get("k")
    cali_idx = tray_data.get("cali_idx")
    if k_value is None and cali_idx is not None and cali_idx in kprofile_map:
        k_value = kprofile_map[cali_idx]
    return k_value, cali_idx


def _ams_tray(tray_data: dict[str, Any]) -> AMSTray:
    return AMSTray(
        id=tray_data.get("id", 0),
        tray_color=tray_data.get("tray_color"),
        tray_type=tray_data.get("tray_type"),
        tray_sub_brands=tray_data.get("tray_sub_brands"),
        tray_id_name=tray_data.get("tray_id_name"),
        tray_info_idx=tray_data.get("tray_info_idx"),
        remain=tray_data.get("remain", 0),
        k=tray_data.get("k"),
        cali_idx=tray_data.get("cali_idx"),
        tag_uid=_sanitize_tag_uid(tray_data.get("tag_uid")),
        tray_uuid=_sanitize_tray_uuid(tray_data.get("tray_uuid")),
        nozzle_temp_min=tray_data.get("nozzle_temp_min"),
        nozzle_temp_max=tray_data.get("nozzle_temp_max"),
        drying_temp=tray_data.get("drying_temp"),
        drying_time=tray_data.get("drying_time"),
        state=tray_data.get("state"),
    )


def _drying_target(
    ams_id: int, trays: list[AMSTray], drying_targets: dict[int, dict[str, Any]]
) -> tuple[int | None, str | None]:
    target = drying_targets.get(ams_id) or {}
    dry_target_temp = _int_or_none(target.get("temp"))
    dry_filament = str(target.get("filament") or "") or None

    if dry_target_temp is None or not dry_filament:
        for tray in trays:
            if tray.tray_type:
                if not dry_filament:
                    dry_filament = str(tray.tray_type)
                if dry_target_temp is None and tray.drying_temp:
                    dry_target_temp = _int_or_none(tray.drying_temp)
                break

    return dry_target_temp, dry_filament


def build_ams_units(
    raw_data: dict[str, Any],
    kprofile_map: dict[int, float],
    drying_targets: dict[int, dict[str, Any]],
) -> tuple[list[AMSUnit], bool]:
    """Build AMS response models from raw MQTT AMS payloads."""
    ams_units: list[AMSUnit] = []
    if "ams" not in raw_data or not isinstance(raw_data["ams"], list):
        return ams_units, False

    for ams_data in raw_data["ams"]:
        if not isinstance(ams_data, dict):
            continue

        trays: list[AMSTray] = []
        for tray_data in ams_data.get("tray", []):
            k_value, cali_idx = _tray_k_value(tray_data, kprofile_map)
            tray_payload = {**tray_data, "k": k_value, "cali_idx": cali_idx}
            trays.append(_ams_tray(tray_payload))

        humidity_value = _int_or_none(ams_data.get("humidity_raw"))
        if humidity_value is None:
            humidity_value = _int_or_none(ams_data.get("humidity"))

        ams_id_int = int(ams_data.get("id", 0))
        dry_target_temp, dry_filament = _drying_target(ams_id_int, trays, drying_targets)

        ams_units.append(
            AMSUnit(
                id=ams_id_int,
                humidity=humidity_value,
                temp=ams_data.get("temp"),
                is_ams_ht=len(trays) == 1,
                tray=trays,
                serial_number=str(ams_data.get("sn") or ams_data.get("serial_number") or ""),
                sw_ver=str(ams_data.get("sw_ver") or ""),
                dry_time=int(ams_data.get("dry_time") or 0),
                dry_target_temp=dry_target_temp,
                dry_filament=dry_filament,
                module_type=str(ams_data.get("module_type") or ""),
            )
        )

    return ams_units, True


def build_virtual_trays(raw_data: dict[str, Any], kprofile_map: dict[int, float]) -> list[AMSTray]:
    """Build virtual tray response models from raw MQTT payloads."""
    vt_tray: list[AMSTray] = []
    if "vt_tray" not in raw_data:
        return vt_tray

    for vt_data in raw_data["vt_tray"]:
        vt_k_value, vt_cali_idx = _tray_k_value(vt_data, kprofile_map)
        tray_id = int(vt_data.get("id", 254))
        vt_tray.append(
            AMSTray(
                id=tray_id,
                tray_color=vt_data.get("tray_color"),
                tray_type=vt_data.get("tray_type"),
                tray_sub_brands=vt_data.get("tray_sub_brands"),
                tray_id_name=vt_data.get("tray_id_name"),
                tray_info_idx=vt_data.get("tray_info_idx"),
                remain=vt_data.get("remain", 0),
                k=vt_k_value,
                cali_idx=vt_cali_idx,
                tag_uid=_sanitize_tag_uid(vt_data.get("tag_uid")),
                tray_uuid=_sanitize_tray_uuid(vt_data.get("tray_uuid")),
                nozzle_temp_min=vt_data.get("nozzle_temp_min"),
                nozzle_temp_max=vt_data.get("nozzle_temp_max"),
            )
        )

    return vt_tray
