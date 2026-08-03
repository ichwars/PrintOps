"""Protocol helpers for Bambu pressure-advance calibration profiles."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class KProfile:
    """Pressure advance calibration profile reported by a printer."""

    slot_id: int
    extruder_id: int
    nozzle_id: str
    nozzle_diameter: str
    filament_id: str
    name: str
    k_value: str
    n_coef: str = "0.000000"
    ams_id: int = 0
    tray_id: int = -1
    setting_id: str | None = None


def parse_kprofile_entries(
    filaments: list,
    response_nozzle: str | None,
    *,
    log_errors: bool,
) -> list[KProfile]:
    """Parse an extrusion_cali_get response using its envelope nozzle size."""
    profiles: list[KProfile] = []
    for index, filament in enumerate(filaments):
        if not isinstance(filament, dict):
            continue
        try:
            profiles.append(
                KProfile(
                    slot_id=filament.get("cali_idx", index),
                    extruder_id=int(filament.get("extruder_id", 0)),
                    nozzle_id=str(filament.get("nozzle_id", "")),
                    nozzle_diameter=str(filament.get("nozzle_diameter") or response_nozzle or "0.4"),
                    filament_id=str(filament.get("filament_id", "")),
                    name=str(filament.get("name", "")),
                    k_value=str(filament.get("k_value", "0.000000")),
                    n_coef=str(filament.get("n_coef", "0.000000")),
                    ams_id=int(filament.get("ams_id", 0)),
                    tray_id=int(filament.get("tray_id", -1)),
                    setting_id=filament.get("setting_id"),
                )
            )
        except (ValueError, TypeError) as error:
            log = logger.warning if log_errors else logger.debug
            log("Failed to parse K-profile: %s", error)
    return profiles


def publish_cali_write(
    mqtt_client: Any,
    topic: str,
    command: dict,
    sequence_id: str,
    pending_acks: dict[str, dict | None],
) -> None:
    """Register and publish a calibration write before its fast ACK arrives."""
    pending_acks[sequence_id] = None
    try:
        mqtt_client.publish(topic, json.dumps(command), qos=1)
    except Exception:
        pending_acks.pop(sequence_id, None)
        raise


async def await_cali_ack(
    pending_acks: dict[str, dict | None],
    sequence_id: str,
    serial_number: str,
    timeout: float,
) -> tuple[bool, str]:
    """Wait for a calibration-write verdict; silence is not a rejection."""
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            ack = pending_acks.get(sequence_id)
            if ack is not None:
                result = str(ack.get("result", "")).lower()
                reason = str(ack.get("reason", "") or "")
                if result == "fail":
                    return (False, reason or "printer reported failure")
                return (True, reason)
            await asyncio.sleep(0.05)
    finally:
        pending_acks.pop(sequence_id, None)
    logger.warning(
        "[%s] No ack for K-profile write seq=%s within %.1fs",
        serial_number,
        sequence_id,
        timeout,
    )
    return (True, "no acknowledgement from printer")
