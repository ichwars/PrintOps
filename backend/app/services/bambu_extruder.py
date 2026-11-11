"""Resolve active H2 trays from current nozzle telemetry, without guessing."""

import logging

from backend.app.services.mqtt_print_provenance import unexpired_tray_target

logger = logging.getLogger("backend.app.services.bambu_mqtt")


def parse_extruder_position(self, data: dict) -> bool:
    """Read which nozzle is active and which tray each nozzle holds.

    From ``device.extruder``: ``state`` bit 8 is the active nozzle, each
    ``info`` entry's ``snow`` names its AMS and slot. Run on a frame before
    its AMS block, because an H2D's tray_now is a bare slot that only the
    extruder data of the same frame places. Returns True when the frame
    carried the active nozzle's snow. A malformed value is skipped, never
    raised: this runs ahead of everything else the frame carries.
    """
    if data.get("command") not in (None, "push_status"):
        return False
    device = data.get("device")
    extruder = device.get("extruder") if isinstance(device, dict) else None
    if not isinstance(extruder, dict):
        return False
    try:
        state_val = int(extruder["state"]) if "state" in extruder else None
    except (TypeError, ValueError):
        state_val = None
    if state_val is not None:
        # Extract bit 8 for extruder position
        new_extruder = (state_val >> 8) & 0x1
        if new_extruder != self.state.active_extruder:
            logger.debug(
                f"[{self.serial_number}] ACTIVE EXTRUDER CHANGED (state bit 8): {self.state.active_extruder} -> {new_extruder} (0=right, 1=left) [state={state_val}]"
            )
            self.state.active_extruder = new_extruder
    extruder_info = extruder.get("info")
    if not isinstance(extruder_info, list) or len(extruder_info) < 2:
        return False
    # Parse H2D snow field (slot now) for accurate tray_now disambiguation
    # snow encodes AMS ID in high byte: ams_id = snow >> 8, slot = snow & 0xFF
    snow_read: set[int] = set()
    for ext_info in extruder_info:
        if not isinstance(ext_info, dict) or "id" not in ext_info or "snow" not in ext_info:
            continue
        try:
            ext_id = int(ext_info["id"])
            snow = int(ext_info["snow"])
        except (TypeError, ValueError):
            continue
        if 0 <= ext_id <= 1 and snow >= 0:
            # Normalize H2D snow value to global tray ID
            ams_id = snow >> 8
            slot = snow & 0xFF
            if 0 <= ams_id <= 7:
                # Regular AMS slot
                global_tray = ams_id * 4 + (slot & 0x03)
                old_val = self.state.h2d_extruder_snow.get(ext_id)
                if old_val != global_tray:
                    logger.debug(
                        f"[{self.serial_number}] H2D extruder[{ext_id}] snow: "
                        f"raw={snow} (AMS {ams_id} slot {slot}) -> global tray {global_tray}"
                    )
                self.state.h2d_extruder_snow[ext_id] = global_tray
            elif ams_id == 254 or ams_id == 255:
                # External spool or unloaded
                normalized = 254 if slot != 255 else 255
                old_val = self.state.h2d_extruder_snow.get(ext_id)
                if old_val != normalized:
                    logger.debug(
                        f"[{self.serial_number}] H2D extruder[{ext_id}] snow: "
                        f"raw={snow} -> {'external' if normalized == 254 else 'unloaded'}"
                    )
                self.state.h2d_extruder_snow[ext_id] = normalized
            elif 128 <= ams_id <= 191:
                # External spool with hub mapping
                old_val = self.state.h2d_extruder_snow.get(ext_id)
                if old_val != ams_id:
                    logger.debug(
                        f"[{self.serial_number}] H2D extruder[{ext_id}] snow: raw={snow} -> external hub {ams_id}"
                    )
                self.state.h2d_extruder_snow[ext_id] = ams_id
            else:
                continue
            snow_read.add(ext_id)
    return self.state.active_extruder in snow_read


def resolve_dual_nozzle_tray(client, slot: int) -> int:
    """Keep the current tray when neither telemetry nor the print places a slot."""
    current = client.state.tray_now
    pending = unexpired_tray_target(client.state)
    if pending is not None:
        client.state.pending_tray_target = None
        if (0 if 128 <= pending <= 191 else pending % 4) == slot:
            return pending
    active = client.state.active_extruder
    snow = client.state.h2d_extruder_snow.get(active)
    snow_slot = (
        snow % 4 if snow is not None and 0 <= snow < 128 else (0 if snow is not None and 128 <= snow <= 191 else -1)
    )
    if snow is not None and snow != 255 and (snow_slot == slot or client._snow_in_frame):
        return snow
    units = []
    for unit, extruder in client.state.ams_extruder_map.items():
        if extruder == active:
            try:
                units.append(int(unit))
            except (TypeError, ValueError):
                continue
    if len(units) != 1 and client._was_running and not client._completion_triggered:
        mapped = client._resolve_local_slot_from_mapping(slot, client.state.raw_data.get("mapping"), units)
        if mapped is not None:
            return mapped
    if len(units) == 1 and 128 <= units[0] <= 191:
        return units[0]
    candidates = [unit for unit in units if 0 <= unit <= 7 or (128 <= unit <= 191 and slot == 0)]
    if len(candidates) == 1:
        unit = candidates[0]
        return unit if unit >= 128 else unit * 4 + slot
    return current
