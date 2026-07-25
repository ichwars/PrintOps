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
from backend.app.schemas.printer import (
    DiagnosticRequest,
    FilaSwitchResponse,
    HMSErrorResponse,
    NozzleInfoResponse,
    NozzleRackSlot,
    PrinterDiagnosticResult,
    PrinterStatus,
    PrintOptionsResponse,
)
from backend.app.services.printer_diagnostic import run_connection_diagnostic
from backend.app.services.printer_manager import (
    get_derived_status_name,
    resolve_plate_id,
    supports_chamber_heater,
    supports_chamber_temp,
    supports_drying,
    supports_drying_while_printing,
)
from backend.app.services.printer_status_ams import build_ams_units, build_kprofile_map, build_virtual_trays

logger = logging.getLogger(__name__)
router = APIRouter(tags=["printers"])


class _PrinterManagerProxy:
    def __getattr__(self, name: str):
        from backend.app.api.routes import printers as printers_routes

        return getattr(printers_routes.printer_manager, name)


printer_manager = _PrinterManagerProxy()


@router.get("/{printer_id}/status", response_model=PrinterStatus)
async def get_printer_status(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Get real-time status of a printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    state = printer_manager.get_status(printer_id)
    if not state:
        return PrinterStatus(
            id=printer_id,
            name=printer.name,
            connected=False,
        )

    # Determine cover URL if there's an active print (including paused)
    cover_url = None
    if state.state in ("RUNNING", "PAUSE") and state.gcode_file:
        cover_url = f"/api/v1/printers/{printer_id}/cover"

    # Convert HMS errors to response format
    hms_errors = [
        HMSErrorResponse(
            code=e.code,
            attr=e.attr,
            module=e.module,
            severity=e.severity,
            actions=e.actions,
            job_id=e.job_id,
            full_code=e.full_code,
        )
        for e in (state.hms_errors or [])
    ]

    # Parse AMS data from raw_data
    ams_units = []
    vt_tray = []
    ams_exists = False
    raw_data = state.raw_data or {}

    # Cached active-cycle drying params (filament + target temp) we sent
    # last; Bambu doesn't echo them on the per-tick AMS push, so the badge
    # needs the cache to render "<filament> @ <temp>°C".
    drying_targets = printer_manager.get_drying_targets(printer_id) or {}
    kprofile_map = build_kprofile_map(state.kprofiles)
    ams_units, ams_exists = build_ams_units(raw_data, kprofile_map, drying_targets)
    vt_tray = build_virtual_trays(raw_data, kprofile_map)

    # Convert nozzle info to response format
    nozzles = [
        NozzleInfoResponse(
            nozzle_type=n.nozzle_type,
            nozzle_diameter=n.nozzle_diameter,
        )
        for n in (state.nozzles or [])
    ]

    # H2C nozzle rack (tool-changer dock positions)
    nozzle_rack = [
        NozzleRackSlot(
            id=n.get("id", 0),
            nozzle_type=n.get("type", ""),
            nozzle_diameter=n.get("diameter", ""),
            wear=n.get("wear"),
            stat=n.get("stat"),
            max_temp=n.get("max_temp", 0),
            serial_number=n.get("serial_number", ""),
            filament_color=n.get("filament_color", ""),
            filament_id=n.get("filament_id", ""),
            filament_type=n.get("filament_type", ""),
        )
        for n in (state.nozzle_rack or [])
    ]

    # Convert print options to response format
    print_options = PrintOptionsResponse(
        spaghetti_detector=state.print_options.spaghetti_detector,
        print_halt=state.print_options.print_halt,
        halt_print_sensitivity=state.print_options.halt_print_sensitivity,
        first_layer_inspector=state.print_options.first_layer_inspector,
        printing_monitor=state.print_options.printing_monitor,
        buildplate_marker_detector=state.print_options.buildplate_marker_detector,
        allow_skip_parts=state.print_options.allow_skip_parts,
        nozzle_clumping_detector=state.print_options.nozzle_clumping_detector,
        nozzle_clumping_sensitivity=state.print_options.nozzle_clumping_sensitivity,
        pileup_detector=state.print_options.pileup_detector,
        pileup_sensitivity=state.print_options.pileup_sensitivity,
        airprint_detector=state.print_options.airprint_detector,
        airprint_sensitivity=state.print_options.airprint_sensitivity,
        auto_recovery_step_loss=state.print_options.auto_recovery_step_loss,
        filament_tangle_detect=state.print_options.filament_tangle_detect,
    )

    # Get AMS mapping from raw_data (which AMS is connected to which nozzle)
    ams_mapping = raw_data.get("ams_mapping", [])
    # Get per-AMS extruder map from state attribute (not raw_data, to avoid race condition
    # where raw_data gets replaced during MQTT updates and ams_extruder_map is temporarily missing)
    ams_extruder_map = state.ams_extruder_map or {}
    logger.debug("API returning ams_mapping: %s, ams_extruder_map: %s", ams_mapping, ams_extruder_map)

    # tray_now from MQTT is already a global tray ID: (ams_id * 4) + slot_id
    # Per OpenBambuAPI docs: 254 = external spool, 255 = no filament, otherwise global tray ID
    # No conversion needed - just use the raw value directly
    tray_now = state.tray_now
    logger.debug("Using tray_now directly as global ID: %s", tray_now)

    # Filter out chamber temp for models that don't have a real sensor
    # P1P, P1S, A1, A1Mini report meaningless chamber_temper values
    temperatures = state.temperatures
    if not supports_chamber_temp(printer.model):
        temperatures = {
            k: v for k, v in temperatures.items() if k not in ("chamber", "chamber_target", "chamber_heating")
        }

    # Resolve the active print's archive + plate (#881 follow-up): lets the
    # printer card show the actual plate name for multi-plate 3MFs instead of
    # just the 3MF filename. Only attempted for active prints, since subtask_id
    # is only meaningful then.
    current_archive_id: int | None = None
    current_plate_id: int | None = None
    if state.state in ("RUNNING", "PAUSE"):
        current_plate_id = resolve_plate_id(state)
        if state.subtask_id:
            from backend.app.models.archive import PrintArchive

            archive_row = await db.execute(
                select(PrintArchive.id)
                .where(PrintArchive.subtask_id == state.subtask_id)
                .where(PrintArchive.printer_id == printer_id)
                .order_by(PrintArchive.created_at.desc())
                .limit(1)
            )
            current_archive_id = archive_row.scalar_one_or_none()

    return PrinterStatus(
        id=printer_id,
        name=printer.name,
        connected=state.connected,
        state=state.state,
        current_print=state.current_print,
        subtask_name=state.subtask_name,
        gcode_file=state.gcode_file,
        progress=state.progress,
        remaining_time=state.remaining_time,
        layer_num=state.layer_num,
        total_layers=state.total_layers,
        temperatures=temperatures,
        cover_url=cover_url,
        hms_errors=hms_errors,
        ams=ams_units,
        ams_exists=ams_exists,
        vt_tray=vt_tray,
        sdcard=state.sdcard,
        store_to_sdcard=state.store_to_sdcard,
        timelapse=state.timelapse,
        ipcam=state.ipcam,
        wifi_signal=state.wifi_signal,
        wired_network=state.wired_network,
        door_open=state.door_open,
        nozzles=nozzles,
        nozzle_rack=nozzle_rack,
        print_options=print_options,
        stg_cur=state.stg_cur,
        stg_cur_name=get_derived_status_name(state, printer.model),
        stg=state.stg,
        airduct_mode=state.airduct_mode,
        speed_level=state.speed_level,
        chamber_light=state.chamber_light,
        active_extruder=state.active_extruder,
        ams_mapping=ams_mapping,
        ams_extruder_map=ams_extruder_map,
        tray_now=tray_now,
        ams_status_main=state.ams_status_main,
        ams_status_sub=state.ams_status_sub,
        mc_print_sub_stage=state.mc_print_sub_stage,
        last_ams_update=state.last_ams_update,
        printable_objects_count=len(state.printable_objects),
        cooling_fan_speed=state.cooling_fan_speed,
        big_fan1_speed=state.big_fan1_speed,
        big_fan2_speed=state.big_fan2_speed,
        heatbreak_fan_speed=state.heatbreak_fan_speed,
        firmware_version=state.firmware_version,
        developer_mode=state.developer_mode if state else None,
        ams_filament_backup=state.ams_filament_backup if state else None,
        awaiting_plate_clear=printer_manager.is_awaiting_plate_clear(printer_id),
        supports_drying=supports_drying(printer.model, state.firmware_version),
        supports_drying_while_printing=supports_drying_while_printing(printer.model, state.firmware_version),
        supports_chamber_heater=supports_chamber_heater(printer.model),
        current_archive_id=current_archive_id,
        current_plate_id=current_plate_id,
        fila_switch=(
            FilaSwitchResponse(
                installed=state.fila_switch.installed,
                in_slots=list(state.fila_switch.in_slots),
                out_extruders=list(state.fila_switch.out_extruders),
                stat=state.fila_switch.stat,
                info=state.fila_switch.info,
            )
            if state.fila_switch and state.fila_switch.installed
            else None
        ),
    )


@router.get("/{printer_id}/current-print-user")
async def get_current_print_user(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Get the user who started the current print (for reprint tracking).

    Returns user info if available, empty object otherwise.
    This tracks users for reprints (which bypass the queue).
    For queue-based prints, use the queue item's created_by field instead.
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    user_info = printer_manager.get_current_print_user(printer_id)
    return user_info or {}


@router.post("/{printer_id}/refresh-status")
async def refresh_printer_status(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Request a full status refresh from the printer (sends pushall command)."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    success = printer_manager.request_status_update(printer_id)
    if not success:
        raise HTTPException(400, "Printer not connected")

    return {"status": "refresh_requested"}


@router.post("/{printer_id}/connect")
async def connect_printer(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Manually connect to a printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    success = await printer_manager.connect_printer(printer)
    return {"connected": success}


@router.post("/{printer_id}/disconnect")
async def disconnect_printer(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Manually disconnect from a printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    printer_manager.disconnect_printer(printer_id)
    return {"connected": False}


@router.post("/test")
async def test_printer_connection(
    ip_address: str,
    serial_number: str,
    access_code: str,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CREATE),
):
    """Test connection to a printer without saving."""
    result = await printer_manager.test_connection(
        ip_address=ip_address,
        serial_number=serial_number,
        access_code=access_code,
    )
    return result


@router.post("/diagnostic", response_model=PrinterDiagnosticResult)
async def diagnose_connection(
    req: DiagnosticRequest,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CREATE),
):
    """Run connection diagnostics for the Add-Printer flow (printer not yet saved).

    When serial_number + access_code are supplied the MQTT credential check
    also runs; otherwise only the network-level checks are performed.
    """
    return await run_connection_diagnostic(
        req.ip_address,
        serial_number=req.serial_number or None,
        access_code=req.access_code or None,
    )


@router.get("/{printer_id}/diagnostic", response_model=PrinterDiagnosticResult)
async def diagnose_printer(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Run connection diagnostics for an existing saved printer.

    On-demand run from the UI: wait up to PUBLISH_WAIT_DEFAULT seconds for the
    printer to publish a status report so a fresh reconnect (counter reset to
    0) isn't reported as `printer_publishing: fail` prematurely. The support
    package code path calls run_connection_diagnostic without the wait so
    bundling stays fast.
    """
    from backend.app.services.printer_diagnostic import PUBLISH_WAIT_DEFAULT

    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")
    return await run_connection_diagnostic(
        printer.ip_address,
        printer=printer,
        wait_for_publish_seconds=PUBLISH_WAIT_DEFAULT,
    )
