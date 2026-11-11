"""Shared REST/WebSocket representation of physical and virtual AMS trays."""

from dataclasses import asdict

from backend.app.schemas.printer import AMSTray, AMSUnit
from backend.app.services.calibration_context import slot_context


def serialize_ams_state(state, model=None, drying_targets=None, raw_data=None) -> tuple[list, list]:
    # Parse AMS data from raw_data
    ams_units = []
    vt_tray = []
    raw_data = (state.raw_data or {}) if raw_data is None else raw_data

    from backend.app.services.calibration_context import slot_k_value

    ams_data_list = raw_data.get("ams")
    if isinstance(ams_data_list, dict):
        ams_data_list = ams_data_list.get("ams")
    if isinstance(ams_data_list, list):
        for ams_data in ams_data_list:
            if not isinstance(ams_data, dict):
                continue
            trays = []
            for tray in ams_data.get("tray", []):
                if not isinstance(tray, dict):
                    continue
                tag_uid = tray.get("tag_uid")
                if tag_uid in ("", "0000000000000000"):
                    tag_uid = None
                tray_uuid = tray.get("tray_uuid")
                if tray_uuid in ("", "00000000000000000000000000000000"):
                    tray_uuid = None

                # Get K value: first try tray's k field, then lookup from K-profiles
                k_value = tray.get("k")
                cali_idx = tray.get("cali_idx")
                if k_value is None:
                    k_value = slot_k_value(
                        state, model, ams_data.get("id"), tray.get("id"), cali_idx, tray.get("tray_info_idx")
                    )

                # P1S / A1 Mini physically-empty-slot signal (#1322 follow-up by
                # @RosdasHH): for a truly empty slot the firmware sends only
                # {"id": N} — no state, no tray_type, no anything else. Treat
                # that as the firmware's "no spool" indicator (state=9) so the
                # assign-spool path in inventory.py can short-circuit a MQTT
                # publish the firmware would silently drop anyway. The
                # post-"Reset Slot" A1 Mini BMCU case sends a populated payload
                # (state=3, tray_type="") — different shape, doesn't match this
                # guard, still attempts the MQTT push per the #1322 fix.
                state_val = tray.get("state")
                if state_val is None and len(tray) == 1 and "id" in tray:
                    state_val = 9

                trays.append(
                    {
                        "id": int(tray.get("id", 0)),
                        "tray_color": tray.get("tray_color"),
                        "tray_type": tray.get("tray_type"),
                        "tray_sub_brands": tray.get("tray_sub_brands"),
                        "tray_id_name": tray.get("tray_id_name"),
                        "tray_info_idx": tray.get("tray_info_idx"),
                        "remain": tray.get("remain", 0),
                        "k": k_value,
                        "cali_idx": cali_idx,
                        "calibration_context": _slot_calibration(state, model, ams_data.get("id"), tray.get("id")),
                        "tag_uid": tag_uid,
                        "tray_uuid": tray_uuid,
                        "nozzle_temp_min": tray.get("nozzle_temp_min"),
                        "nozzle_temp_max": tray.get("nozzle_temp_max"),
                        "drying_temp": tray.get("drying_temp"),
                        "drying_time": tray.get("drying_time"),
                        "state": state_val,
                        "exists": tray.get("exists"),
                    }
                )
            # Prefer humidity_raw (actual percentage) over humidity (index 1-5)
            humidity_raw = ams_data.get("humidity_raw")
            humidity_idx = ams_data.get("humidity")
            humidity_value = None

            if humidity_raw is not None:
                try:
                    humidity_value = int(humidity_raw)
                except (ValueError, TypeError):
                    pass  # Skip unparseable humidity; will try index fallback
            # Fall back to index if no raw value (index is 1-5, not percentage)
            if humidity_value is None and humidity_idx is not None:
                try:
                    humidity_value = int(humidity_idx)
                except (ValueError, TypeError):
                    pass  # Skip unparseable humidity index; humidity remains None

            # AMS-HT has 1 tray, regular AMS has 4 trays
            is_ams_ht = 128 <= int(ams_data.get("id", 0)) <= 135

            # Active-cycle filament + target temperature for the badge.
            # Bambu does not echo the cycle's chosen filament/temp on the
            # per-tick AMS push, so prefer the cached target from the last
            # ``send_drying_command``. When we have no record (drying
            # started in a previous backend lifetime, or the cache was
            # never seeded), fall back to the first loaded tray's
            # tray_type + RFID-recommended drying_temp — the same heuristic
            # the popover already uses to seed defaults.
            ams_id_int = int(ams_data.get("id", 0))
            target = (drying_targets or {}).get(ams_id_int)
            dry_target_temp: int | None = None
            dry_filament: str | None = None
            if target:
                temp_val = target.get("temp")
                fil_val = target.get("filament") or ""
                if temp_val is not None:
                    try:
                        dry_target_temp = int(temp_val)
                    except (TypeError, ValueError):
                        dry_target_temp = None
                if fil_val:
                    dry_filament = str(fil_val)
            if dry_target_temp is None or not dry_filament:
                for tray in trays:
                    if tray.get("tray_type"):
                        if not dry_filament:
                            dry_filament = str(tray["tray_type"])
                        if dry_target_temp is None and tray.get("drying_temp"):
                            try:
                                dry_target_temp = int(tray["drying_temp"])
                            except (TypeError, ValueError):
                                pass
                        break

            ams_units.append(
                {
                    "id": ams_id_int,
                    "humidity": humidity_value,
                    "temp": ams_data.get("temp"),
                    "is_ams_ht": is_ams_ht,
                    "tray": trays,
                    # Serial number: Bambu MQTT uses "sn" key on AMS unit objects
                    "serial_number": str(ams_data.get("sn") or ams_data.get("serial_number") or ""),
                    # Firmware version: populated by _handle_version_info from get_version
                    "sw_ver": str(ams_data.get("sw_ver") or ""),
                    # Drying: dry_time > 0 means drying is active (minutes remaining)
                    "dry_time": int(ams_data.get("dry_time") or 0),
                    # Drying status from info hex bits (0=Off, 1=Checking, 2=Drying, 3=Cooling, etc.)
                    "dry_status": int(ams_data.get("dry_status") or 0),
                    "dry_sub_status": int(ams_data.get("dry_sub_status") or 0),
                    # Cannot-dry reasons from firmware (e.g. 1=InsufficientPower, 8=NeedPluginPower)
                    "dry_sf_reason": list(ams_data.get("dry_sf_reason") or []),
                    # Active-cycle filament name + target temperature
                    "dry_target_temp": dry_target_temp,
                    "dry_filament": dry_filament,
                    # Module type: "ams", "n3f", "n3s" (from get_version)
                    "module_type": str(ams_data.get("module_type") or ""),
                }
            )

    # Parse virtual tray (external spool) — now a list
    if "vt_tray" in raw_data:
        vt_tray_raw = raw_data["vt_tray"]
        # Defensive: MQTT sends vt_tray as a dict; normalize to list
        if isinstance(vt_tray_raw, dict):
            vt_tray_raw = [vt_tray_raw]
        elif not isinstance(vt_tray_raw, list):
            vt_tray_raw = []
        for vt_data in vt_tray_raw:
            if not isinstance(vt_data, dict):
                continue
            vt_tag_uid = vt_data.get("tag_uid")
            if vt_tag_uid in ("", "0000000000000000"):
                vt_tag_uid = None
            vt_tray_uuid = vt_data.get("tray_uuid")
            if vt_tray_uuid in ("", "00000000000000000000000000000000"):
                vt_tray_uuid = None

            # Get K value for vt_tray
            vt_k_value = vt_data.get("k")
            vt_cali_idx = vt_data.get("cali_idx")
            if vt_k_value is None:
                vt_k_value = slot_k_value(
                    state, model, 255, vt_data.get("id"), vt_cali_idx, vt_data.get("tray_info_idx")
                )

            tray_id = int(vt_data.get("id", 254))
            vt_tray.append(
                {
                    "id": tray_id,
                    "tray_color": vt_data.get("tray_color"),
                    "tray_type": vt_data.get("tray_type"),
                    "tray_sub_brands": vt_data.get("tray_sub_brands"),
                    "tray_id_name": vt_data.get("tray_id_name"),
                    "tray_info_idx": vt_data.get("tray_info_idx"),
                    "remain": vt_data.get("remain", 0),
                    "k": vt_k_value,
                    "cali_idx": vt_cali_idx,
                    "calibration_context": _slot_calibration(state, model, 255, tray_id - 254),
                    "tag_uid": vt_tag_uid,
                    "tray_uuid": vt_tray_uuid,
                    "nozzle_temp_min": vt_data.get("nozzle_temp_min"),
                    "nozzle_temp_max": vt_data.get("nozzle_temp_max"),
                    "drying_temp": vt_data.get("drying_temp"),
                    "drying_time": vt_data.get("drying_time"),
                    "state": vt_data.get("state"),
                    "exists": vt_data.get("exists"),
                }
            )

    return ams_units, vt_tray


def build_ams_units(raw_data, state, drying_targets, model=None) -> tuple[list[AMSUnit], bool]:
    units, _ = serialize_ams_state(state, model, drying_targets, raw_data)
    return [AMSUnit(**unit) for unit in units], bool(units)


def build_virtual_trays(raw_data, state, model=None) -> list[AMSTray]:
    _, trays = serialize_ams_state(state, model, raw_data=raw_data)
    return [AMSTray(**tray) for tray in trays]


def _slot_calibration(state, model, ams_id, tray_id):
    context = slot_context(state, model, ams_id, tray_id)
    return asdict(context) if context is not None else None
