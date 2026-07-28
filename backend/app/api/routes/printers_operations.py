import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    RequirePermissionIfAuthEnabled,
)
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.printer import Printer
from backend.app.models.slot_preset import SlotPresetMapping
from backend.app.services.printer_manager import (
    drying_screen_only,
    supports_drying,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["printers"])

_DRYING_SCREEN_ONLY_DETAIL = "This printer only supports AMS drying from its own screen"


class _PrinterManagerProxy:
    def __getattr__(self, name: str):
        from backend.app.api.routes import printers as printers_routes

        return getattr(printers_routes.printer_manager, name)


printer_manager = _PrinterManagerProxy()


@router.post("/{printer_id}/logging/enable")
async def enable_mqtt_logging(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Enable MQTT message logging for a printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    success = printer_manager.enable_logging(printer_id, True)
    if not success:
        raise HTTPException(400, "Printer not connected")

    return {"logging_enabled": True}


@router.post("/{printer_id}/logging/disable")
async def disable_mqtt_logging(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Disable MQTT message logging for a printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    success = printer_manager.enable_logging(printer_id, False)
    if not success:
        raise HTTPException(400, "Printer not connected")

    return {"logging_enabled": False}


@router.get("/{printer_id}/logging")
async def get_mqtt_logs(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Get MQTT message logs for a printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    logs = printer_manager.get_logs(printer_id)
    return {
        "logging_enabled": printer_manager.is_logging_enabled(printer_id),
        "logs": [
            {
                "timestamp": log.timestamp,
                "topic": log.topic,
                "direction": log.direction,
                "payload": log.payload,
            }
            for log in logs
        ],
    }


@router.delete("/{printer_id}/logging")
async def clear_mqtt_logs(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Clear MQTT message logs for a printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    printer_manager.clear_logs(printer_id)
    return {"status": "cleared"}


@router.post("/{printer_id}/drying/start")
async def start_drying(
    printer_id: int,
    ams_id: int,
    temp: int = 45,
    duration: int = 4,
    filament: str = "",
    rotate_tray: bool = False,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Send AMS drying start command. temp=45-85, duration=hours."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    # Server-side guard: reject if this model/firmware doesn't support drying
    live_state = printer_manager.get_status(printer_id)
    firmware = live_state.firmware_version if live_state else None
    if drying_screen_only(printer.model):
        raise HTTPException(400, _DRYING_SCREEN_ONLY_DETAIL)
    if not supports_drying(printer.model, firmware):
        raise HTTPException(400, "Drying not supported for this printer model or firmware version")

    if temp < 45 or temp > 85:
        raise HTTPException(400, "Temperature must be 45-85°C")
    if duration < 1 or duration > 24:
        raise HTTPException(400, "Duration must be 1-24 hours")

    # Inspect the live AMS unit: surface blocking dry_sf_reasons (otherwise the
    # firmware silently ignores the command — #971) and backfill an empty
    # filament field from the first loaded tray so the printer doesn't reject
    # the payload.
    target_ams: dict | None = None
    for unit in (live_state.raw_data.get("ams") if live_state else None) or []:
        try:
            if int(unit.get("id", -1)) == ams_id:
                target_ams = unit
                break
        except (TypeError, ValueError):
            continue

    if target_ams is not None:
        reason_messages = {
            0: "Printer is busy",
            1: "Insufficient power — too many AMS drying or external PSU required",
            2: "AMS is busy",
            3: "Filament is at the AMS outlet — retract it first",
            4: "AMS is already starting a drying cycle",
            5: "Not supported in 2D mode",
            6: "AMS is already drying",
            7: "AMS firmware is upgrading",
            8: "Plug in the external AMS power adapter to start drying",
        }
        for code in target_ams.get("dry_sf_reason") or []:
            try:
                code_int = int(code)
            except (TypeError, ValueError):
                continue
            if code_int in reason_messages:
                raise HTTPException(409, reason_messages[code_int])

        if not filament:
            for tray in target_ams.get("tray") or []:
                tray_type = tray.get("tray_type")
                if tray_type:
                    filament = str(tray_type)
                    break

    if not filament:
        filament = "PLA"

    success = printer_manager.send_drying_command(
        printer_id, ams_id, temp, duration, mode=1, filament=filament, rotate_tray=rotate_tray
    )
    if not success:
        raise HTTPException(400, "Printer not connected")
    return {"status": "drying_started", "ams_id": ams_id, "temp": temp, "duration": duration}


@router.post("/{printer_id}/drying/stop")
async def stop_drying(
    printer_id: int,
    ams_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Send AMS drying stop command."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    if drying_screen_only(printer.model):
        raise HTTPException(400, _DRYING_SCREEN_ONLY_DETAIL)

    success = printer_manager.send_drying_command(printer_id, ams_id, temp=0, duration=0, mode=0)
    if not success:
        raise HTTPException(400, "Printer not connected")
    return {"status": "drying_stopped", "ams_id": ams_id}


@router.post("/{printer_id}/print-options")
async def set_print_option(
    printer_id: int,
    module_name: str,
    enabled: bool,
    print_halt: bool = True,
    sensitivity: str = "medium",
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Set an AI detection / print option on the printer.

    Valid module_name values:
    - spaghetti_detector: Spaghetti detection
    - first_layer_inspector: First layer inspection
    - printing_monitor: AI print quality monitoring
    - buildplate_marker_detector: Build plate marker detection
    - allow_skip_parts: Allow skipping failed parts
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client or not client.state.connected:
        raise HTTPException(400, "Printer not connected")

    # Validate module_name
    valid_modules = [
        "spaghetti_detector",
        "first_layer_inspector",
        "printing_monitor",
        "buildplate_marker_detector",
        "allow_skip_parts",
        "pileup_detector",
        "clump_detector",
        "airprint_detector",
        "auto_recovery_step_loss",
    ]
    if module_name not in valid_modules:
        raise HTTPException(400, f"Invalid module_name. Must be one of: {valid_modules}")

    # Validate sensitivity
    valid_sensitivities = ["low", "medium", "high", "never_halt"]
    if sensitivity not in valid_sensitivities:
        raise HTTPException(400, f"Invalid sensitivity. Must be one of: {valid_sensitivities}")

    success = client.set_xcam_option(
        module_name=module_name,
        enabled=enabled,
        print_halt=print_halt,
        sensitivity=sensitivity,
    )

    if not success:
        raise HTTPException(500, "Failed to send command to printer")

    return {
        "success": True,
        "module_name": module_name,
        "enabled": enabled,
        "print_halt": print_halt,
        "sensitivity": sensitivity,
    }


@router.post("/{printer_id}/ams-backup")
async def set_ams_backup(
    printer_id: int,
    enabled: bool,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Toggle AMS Filament Backup (auto-switch to a backup spool when one runs out)."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client or not client.state.connected:
        raise HTTPException(400, "Printer not connected")

    success = client.set_ams_filament_backup(enabled)
    if not success:
        raise HTTPException(500, "Failed to send command to printer")

    return {"success": True, "ams_filament_backup": enabled}


@router.get("/{printer_id}/inventory-remain")
async def get_inventory_remain(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Per-globalTrayId remaining grams for slots bound to an inventory spool.

    Mirrors `_build_inventory_remain_overrides` server-side so the PrintModal
    client can apply the same two-tier "Prefer Lowest Remaining Filament" sort
    the dispatcher uses (#1766). Works for both internal inventory and
    Spoolman; unbound slots are absent from the map (client falls back to the
    printer's MQTT `remain` for those).
    """
    from backend.app.services.print_scheduler import PrintScheduler

    state = printer_manager.get_status(printer_id)
    if not state:
        return {"inventory_remain_g": {}}

    scheduler = PrintScheduler()
    loaded = scheduler._build_loaded_filaments(state)
    overrides = await scheduler._build_inventory_remain_overrides(db, printer_id, loaded)
    return {"inventory_remain_g": {str(k): v for k, v in overrides.items()}}


@router.post("/{printer_id}/calibration")
async def start_calibration(
    printer_id: int,
    bed_leveling: bool = False,
    vibration: bool = False,
    motor_noise: bool = False,
    nozzle_offset: bool = False,
    high_temp_heatbed: bool = False,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Start printer calibration with selected options.

    At least one option must be selected.

    Options:
    - bed_leveling: Run bed leveling calibration
    - vibration: Run vibration compensation calibration
    - motor_noise: Run motor noise cancellation calibration
    - nozzle_offset: Run nozzle offset calibration (dual nozzle printers)
    - high_temp_heatbed: Run high-temperature heatbed calibration
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client or not client.state.connected:
        raise HTTPException(400, "Printer not connected")

    # Check that at least one option is selected
    if not any([bed_leveling, vibration, motor_noise, nozzle_offset, high_temp_heatbed]):
        raise HTTPException(400, "At least one calibration option must be selected")

    success = client.start_calibration(
        bed_leveling=bed_leveling,
        vibration=vibration,
        motor_noise=motor_noise,
        nozzle_offset=nozzle_offset,
        high_temp_heatbed=high_temp_heatbed,
    )

    if not success:
        raise HTTPException(500, "Failed to send calibration command to printer")

    return {
        "success": True,
        "bed_leveling": bed_leveling,
        "vibration": vibration,
        "motor_noise": motor_noise,
        "nozzle_offset": nozzle_offset,
        "high_temp_heatbed": high_temp_heatbed,
    }


def _slot_preset_key(ams_id: int, tray_id: int) -> int:
    # Mirrors frontend getGlobalTrayId (amsHelpers.ts): AMS-HT (128-135) is keyed
    # by ams_id since each unit has a single slot and shares its global ID with
    # the unit itself. Regular AMS and external (255) use ams_id*4+tray_id.
    if 128 <= ams_id <= 135:
        return ams_id
    return ams_id * 4 + tray_id


@router.get("/{printer_id}/slot-presets")
async def get_slot_presets(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Get all saved slot-to-preset mappings for a printer."""
    result = await db.execute(select(SlotPresetMapping).where(SlotPresetMapping.printer_id == printer_id))
    mappings = result.scalars().all()

    return {
        _slot_preset_key(mapping.ams_id, mapping.tray_id): {
            "ams_id": mapping.ams_id,
            "tray_id": mapping.tray_id,
            "preset_id": mapping.preset_id,
            "preset_name": mapping.preset_name,
        }
        for mapping in mappings
    }


@router.get("/{printer_id}/slot-presets/{ams_id}/{tray_id}")
async def get_slot_preset(
    printer_id: int,
    ams_id: int,
    tray_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Get the saved preset for a specific slot."""
    result = await db.execute(
        select(SlotPresetMapping).where(
            SlotPresetMapping.printer_id == printer_id,
            SlotPresetMapping.ams_id == ams_id,
            SlotPresetMapping.tray_id == tray_id,
        )
    )
    mapping = result.scalar_one_or_none()

    if not mapping:
        return None

    return {
        "ams_id": mapping.ams_id,
        "tray_id": mapping.tray_id,
        "preset_id": mapping.preset_id,
        "preset_name": mapping.preset_name,
    }


@router.put("/{printer_id}/slot-presets/{ams_id}/{tray_id}")
async def save_slot_preset(
    printer_id: int,
    ams_id: int,
    tray_id: int,
    preset_id: str,
    preset_name: str,
    preset_source: str = "cloud",
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
    db: AsyncSession = Depends(get_db),
):
    """Save a preset mapping for a specific slot."""
    # Check printer exists
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Printer not found")

    # Check for existing mapping
    result = await db.execute(
        select(SlotPresetMapping).where(
            SlotPresetMapping.printer_id == printer_id,
            SlotPresetMapping.ams_id == ams_id,
            SlotPresetMapping.tray_id == tray_id,
        )
    )
    mapping = result.scalar_one_or_none()

    if mapping:
        # Update existing
        mapping.preset_id = preset_id
        mapping.preset_name = preset_name
        mapping.preset_source = preset_source
    else:
        # Create new
        mapping = SlotPresetMapping(
            printer_id=printer_id,
            ams_id=ams_id,
            tray_id=tray_id,
            preset_id=preset_id,
            preset_name=preset_name,
            preset_source=preset_source,
        )
        db.add(mapping)

    await db.commit()
    await db.refresh(mapping)

    return {
        "ams_id": mapping.ams_id,
        "tray_id": mapping.tray_id,
        "preset_id": mapping.preset_id,
        "preset_name": mapping.preset_name,
        "preset_source": mapping.preset_source,
    }


@router.delete("/{printer_id}/slot-presets/{ams_id}/{tray_id}")
async def delete_slot_preset(
    printer_id: int,
    ams_id: int,
    tray_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
    db: AsyncSession = Depends(get_db),
):
    """Delete a saved preset mapping for a slot."""
    result = await db.execute(
        select(SlotPresetMapping).where(
            SlotPresetMapping.printer_id == printer_id,
            SlotPresetMapping.ams_id == ams_id,
            SlotPresetMapping.tray_id == tray_id,
        )
    )
    mapping = result.scalar_one_or_none()

    if mapping:
        await db.delete(mapping)
        await db.commit()

    return {"success": True}
