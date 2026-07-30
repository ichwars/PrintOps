import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.cloud import build_authenticated_cloud, resolve_api_key_cloud_owner
from backend.app.core.auth import (
    RequirePermissionIfAuthEnabled,
    is_auth_enabled,
)
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.printer import Printer
from backend.app.models.user import User
from backend.app.schemas.printer import (
    HmsActionBody,
)
from backend.app.services.bambu_cloud import BambuCloudAuthError, BambuCloudError
from backend.app.services.printer_manager import (
    resolve_plate_id,
    supports_chamber_heater,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["printers"])


class _PrinterManagerProxy:
    def __getattr__(self, name: str):
        from backend.app.api.routes import printers as printers_routes

        return getattr(printers_routes.printer_manager, name)


printer_manager = _PrinterManagerProxy()


def _hms_action_ack_wait_seconds() -> float:
    from backend.app.api.routes import printers as printers_routes

    return printers_routes.HMS_ACTION_ACK_WAIT_SECONDS


async def _publish_cloud_print_command(
    printer: Printer,
    payload: dict | list[dict],
    db: AsyncSession,
    current_user: User | None,
) -> dict:
    if current_user is None and await is_auth_enabled(db):
        raise HTTPException(
            403,
            {
                "code": "cloud_control_scope_required",
                "message": "Cloud control requires a signed-in user or an API key with cloud access.",
            },
        )
    cloud = await build_authenticated_cloud(db, current_user)
    if cloud is None or not cloud.is_authenticated:
        raise HTTPException(
            400,
            {
                "code": "cloud_control_not_configured",
                "message": "Bambu Cloud is not configured for this user.",
            },
        )
    try:
        payloads = payload if isinstance(payload, list) else [payload]
        for command_payload in payloads:
            await cloud.publish_mqtt_command(printer.serial_number, command_payload)
        return {"success": True, "control_channel": "cloud"}
    except BambuCloudAuthError as exc:
        raise HTTPException(
            401,
            {
                "code": "cloud_control_auth_failed",
                "message": str(exc),
            },
        ) from exc
    except BambuCloudError as exc:
        raise HTTPException(
            502,
            {
                "code": "cloud_control_failed",
                "message": str(exc),
            },
        ) from exc
    finally:
        await cloud.close()


async def _send_print_command_with_cloud_fallback(
    printer_id: int,
    *,
    command: dict | list[dict],
    local_send,
    local_failure_message: str,
    success_message: str,
    db: AsyncSession,
    current_user: User | None,
) -> dict:
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    state = printer_manager.get_status(printer_id)
    client = printer_manager.get_client(printer_id)
    if client and state and state.connected and state.developer_mode is not False:
        success = local_send(client)
        if not success:
            raise HTTPException(500, local_failure_message)
        return {"success": True, "message": success_message, "control_channel": "local"}

    if state and state.connected and state.developer_mode is False:
        cloud_result = await _publish_cloud_print_command(printer, command, db, current_user)
        return {
            **cloud_result,
            "message": f"{success_message} via Bambu Cloud",
        }

    if not client:
        raise HTTPException(400, "Printer not connected")

    raise HTTPException(400, "Local printer control unavailable")


@router.post("/{printer_id}/debug/simulate-print-complete")
async def debug_simulate_print_complete(
    printer_id: int,
    db: AsyncSession = Depends(get_db),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
):
    """DEBUG: Simulate print completion to test freeze behavior.

    This triggers the same code path as a real print completion,
    without needing to wait for an actual print to finish.
    """
    from backend.app.main import _active_prints, on_print_complete
    from backend.app.models.archive import PrintArchive

    # Get the most recent archive for this printer
    result = await db.execute(
        select(PrintArchive)
        .where(PrintArchive.printer_id == printer_id)
        .order_by(PrintArchive.created_at.desc())
        .limit(1)
    )
    archive = result.scalar_one_or_none()

    if not archive:
        raise HTTPException(status_code=404, detail="No archives found for this printer")

    # Register this archive as "active" so on_print_complete can find it
    filename = archive.file_path.split("/")[-1] if archive.file_path else "test.3mf"
    subtask_name = archive.print_name or "Test Print"
    _active_prints[(printer_id, filename)] = archive.id
    _active_prints[(printer_id, subtask_name)] = archive.id

    # Simulate print completion data
    data = {
        "status": "completed",
        "filename": filename,
        "subtask_name": subtask_name,
        "timelapse_was_active": False,
    }

    logger.info("Simulating print complete for printer %s, archive %s", printer_id, archive.id)

    # Call the actual on_print_complete handler
    await on_print_complete(printer_id, data)

    return {"success": True, "archive_id": archive.id, "message": "Print completion simulated"}


@router.post("/{printer_id}/print/stop")
async def stop_print(
    printer_id: int,
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = Depends(get_db),
):
    """Stop/cancel the current print job."""
    result = await _send_print_command_with_cloud_fallback(
        printer_id,
        command={"print": {"command": "stop", "sequence_id": "0"}},
        local_send=lambda client: client.stop_print(),
        local_failure_message="Failed to stop print",
        success_message="Print stop command sent",
        db=db,
        current_user=current_user or cloud_owner,
    )

    # Mark this printer as user-stopped so on_print_complete reclassifies
    # the resulting "failed"/"aborted" MQTT status as "cancelled" — otherwise
    # the HMS heuristic in _dispatch_archive_update mislabels user-cancels
    # (e.g. the H2D's cancel-sequence module-0x0C HMS) as "Layer shift".
    try:
        from backend.app.main import mark_printer_stopped_by_user

        mark_printer_stopped_by_user(printer_id)
    except Exception as _mark_err:
        logger.warning("Failed to mark printer %s as user-stopped: %s", printer_id, _mark_err)

    return result


@router.post("/{printer_id}/clear-plate")
async def clear_plate(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CLEAR_PLATE),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge that the build plate has been cleared after a finished/failed print.

    Sets a plate-cleared flag so the scheduler can start the next queued print.
    No MQTT command is sent to the printer — the scheduler's start_print command
    will override the FINISH/FAILED state when it sends the next job.
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    if not printer_manager.is_connected(printer_id):
        raise HTTPException(400, "Printer not connected")

    # Accept the acknowledgment whenever the printer is awaiting it — not only when the
    # reported state is FINISH/FAILED. After a power cycle the printer boots into IDLE
    # but the awaiting flag persists, and the user still needs a way to ack it (#961).
    state = printer_manager.get_status(printer_id)
    awaiting = printer_manager.is_awaiting_plate_clear(printer_id)
    if not awaiting and (not state or state.state not in ("FINISH", "FAILED")):
        raise HTTPException(
            400,
            f"Printer is not awaiting plate-clear acknowledgment (state={state.state if state else 'unknown'})",
        )

    printer_manager.set_awaiting_plate_clear(printer_id, False)

    return {"success": True, "message": "Plate cleared, next print will start shortly"}


@router.post("/{printer_id}/print/pause")
async def pause_print(
    printer_id: int,
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = Depends(get_db),
):
    """Pause the current print job."""
    return await _send_print_command_with_cloud_fallback(
        printer_id,
        command={"print": {"command": "pause", "sequence_id": "0"}},
        local_send=lambda client: client.pause_print(),
        local_failure_message="Failed to pause print",
        success_message="Print pause command sent",
        db=db,
        current_user=current_user or cloud_owner,
    )


@router.post("/{printer_id}/print/resume")
async def resume_print(
    printer_id: int,
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused print job."""
    return await _send_print_command_with_cloud_fallback(
        printer_id,
        command={"print": {"command": "resume", "sequence_id": "0"}},
        local_send=lambda client: client.resume_print(),
        local_failure_message="Failed to resume print",
        success_message="Print resume command sent",
        db=db,
        current_user=current_user or cloud_owner,
    )


@router.post("/{printer_id}/print-speed")
async def set_print_speed(
    printer_id: int,
    mode: int = Query(..., description="Speed mode (1=silent, 2=standard, 3=sport, 4=ludicrous)"),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = Depends(get_db),
):
    """Set the print speed mode."""
    if mode not in (1, 2, 3, 4):
        raise HTTPException(422, "Invalid speed mode")

    speed_names = {1: "Silent", 2: "Standard", 3: "Sport", 4: "Ludicrous"}
    return await _send_print_command_with_cloud_fallback(
        printer_id,
        command={"print": {"command": "print_speed", "param": str(mode), "sequence_id": "0"}},
        local_send=lambda client: client.set_print_speed(mode),
        local_failure_message="Failed to set print speed",
        success_message=f"Print speed set to {speed_names.get(mode, 'Unknown')}",
        db=db,
        current_user=current_user or cloud_owner,
    )


@router.post("/{printer_id}/temperature/nozzle")
async def set_nozzle_temperature(
    printer_id: int,
    target: int = Query(..., ge=0, le=320, description="Target nozzle temperature in Celsius; 0 turns heating off"),
    nozzle: int = Query(0, ge=0, le=1, description="Nozzle/extruder index (0=right/default, 1=left)"),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = Depends(get_db),
):
    """Set a nozzle target temperature."""
    return await _send_print_command_with_cloud_fallback(
        printer_id,
        command={"print": {"command": "gcode_line", "param": f"M104 T{nozzle} S{target}", "sequence_id": "0"}},
        local_send=lambda client: client.set_nozzle_temperature(target, nozzle),
        local_failure_message="Failed to set nozzle temperature",
        success_message=f"Nozzle temperature set to {target}°C",
        db=db,
        current_user=current_user or cloud_owner,
    )


@router.post("/{printer_id}/temperature/bed")
async def set_bed_temperature(
    printer_id: int,
    target: int = Query(..., ge=0, le=140, description="Target bed temperature in Celsius; 0 turns heating off"),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = Depends(get_db),
):
    """Set the bed target temperature."""
    return await _send_print_command_with_cloud_fallback(
        printer_id,
        command={"print": {"command": "gcode_line", "param": f"M140 S{target}", "sequence_id": "0"}},
        local_send=lambda client: client.set_bed_temperature(target),
        local_failure_message="Failed to set bed temperature",
        success_message=f"Bed temperature set to {target}°C",
        db=db,
        current_user=current_user or cloud_owner,
    )


@router.post("/{printer_id}/temperature/chamber")
async def set_chamber_temperature(
    printer_id: int,
    target: int = Query(..., ge=0, le=60, description="Target chamber temperature in Celsius; 0 turns heating off"),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = Depends(get_db),
):
    """Set the chamber target temperature.

    Gated on `supports_chamber_heater(model)`: only H2C, H2D, H2D Pro, H2S,
    and X2D have an active chamber heater. Sensor-only models (X1C, X1E,
    P2S) report chamber temp but silently swallow M141, so we 400 here
    rather than send a no-op.
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    if not supports_chamber_heater(printer.model):
        raise HTTPException(400, f"Model {printer.model or 'unknown'} does not have an active chamber heater")

    return await _send_print_command_with_cloud_fallback(
        printer_id,
        command={"print": {"command": "gcode_line", "param": f"M141 S{target}", "sequence_id": "0"}},
        local_send=lambda client: client.set_chamber_temperature(target),
        local_failure_message="Failed to set chamber temperature",
        success_message=f"Chamber temperature set to {target}°C",
        db=db,
        current_user=current_user or cloud_owner,
    )


@router.post("/{printer_id}/fan-speed")
async def set_fan_speed(
    printer_id: int,
    fan: str = Query(..., description="Fan to control: part, aux, or chamber"),
    speed: int = Query(..., ge=0, le=100, description="Fan speed percentage"),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = Depends(get_db),
):
    """Set a fan speed by percentage."""
    fan_ids = {"part": 1, "aux": 2, "chamber": 3}
    fan_id = fan_ids.get(fan)
    if fan_id is None:
        raise HTTPException(400, "fan must be 'part', 'aux', or 'chamber'")

    pwm_speed = round(speed * 255 / 100)
    fan_names = {"part": "Part cooling fan", "aux": "Auxiliary fan", "chamber": "Chamber fan"}
    return await _send_print_command_with_cloud_fallback(
        printer_id,
        command={"print": {"command": "gcode_line", "param": f"M106 P{fan_id} S{pwm_speed}", "sequence_id": "0"}},
        local_send=lambda client: client.set_fan_speed(fan_id, pwm_speed),
        local_failure_message="Failed to set fan speed",
        success_message=f"{fan_names[fan]} set to {speed}%",
        db=db,
        current_user=current_user or cloud_owner,
    )


@router.post("/{printer_id}/select-extruder")
async def select_extruder(
    printer_id: int,
    extruder: int = Query(..., ge=0, le=1, description="Extruder index (0=right, 1=left)"),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Select the active extruder/nozzle on dual-nozzle printers."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    success = client.select_extruder(extruder)
    if not success:
        raise HTTPException(500, "Failed to select nozzle")

    return {"success": True, "message": f"{'Left' if extruder == 1 else 'Right'} nozzle selected"}


@router.post("/{printer_id}/airduct-mode")
async def set_airduct_mode(
    printer_id: int,
    mode: str = Query(..., description="Airduct mode: 'cooling' or 'heating'"),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Set the airduct mode (cooling/heating) on supported printers (P2S/H2*)."""
    if mode not in ("cooling", "heating"):
        raise HTTPException(400, "Mode must be 'cooling' or 'heating'")

    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    success = client.set_airduct_mode(mode)
    if not success:
        raise HTTPException(500, "Failed to set airduct mode")

    return {"success": True, "message": f"Airduct mode set to {mode}"}


@router.post("/{printer_id}/chamber-light")
async def set_chamber_light(
    printer_id: int,
    on: bool = Query(..., description="True to turn on, False to turn off"),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = Depends(get_db),
):
    """Turn the chamber light on or off."""
    mode = "on" if on else "off"
    light_commands = [
        {
            "system": {
                "command": "ledctrl",
                "led_node": led_node,
                "led_mode": mode,
                "led_on_time": 500,
                "led_off_time": 500,
                "loop_times": 0,
                "interval_time": 0,
                "sequence_id": str(index),
            }
        }
        for index, led_node in enumerate(["chamber_light", "chamber_light2"])
    ]
    return await _send_print_command_with_cloud_fallback(
        printer_id,
        command=light_commands,
        local_send=lambda client: client.set_chamber_light(on),
        local_failure_message="Failed to control chamber light",
        success_message=f"Chamber light {'on' if on else 'off'}",
        db=db,
        current_user=current_user or cloud_owner,
    )


@router.post("/{printer_id}/bed-jog")
async def bed_jog(
    printer_id: int,
    distance: float = Query(
        ...,
        description=(
            "Signed nozzle-bed gap adjustment in mm. Negative = decrease gap "
            '("up" arrow in the UI: bed up on bed-on-Z models, toolhead down '
            "on A1 bed-slingers). Positive = increase gap. The backend "
            "translates this into the right G-code Z sign per printer model."
        ),
    ),
    force: bool = Query(False, description="If true, bypass soft endstops via M211 (for use when Z is not homed)"),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Adjust the nozzle-bed gap by a relative distance.

    Emits a short G-code sequence via MQTT. When ``force`` is true the soft
    endstops are disabled for the duration of the move, matching the
    "ignore and move anyway" option Bambu Studio offers when the printer
    is not homed.

    Direction handling: on bed-on-Z printers (X1 / P1 / H2 family) the bed
    is the Z-axis, and Bambu's home convention puts Z=0 at the top with
    Z+ moving the bed down — so a frontend "Up" (decrease gap) maps
    naturally to ``G1 Z-``. On bed-slingers (A1 / A1 Mini) the Z-axis is
    the *toolhead*, and ``G1 Z-`` instead drives the nozzle DOWN into the
    bed (#1334 reported exactly that crash). For those models we invert
    the sign before emitting the G-code, so the UI semantics stay the
    same regardless of which part physically moves.
    """
    if distance == 0 or abs(distance) > 200:
        raise HTTPException(400, "Distance must be non-zero and ≤ 200 mm")

    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    from backend.app.services.printer_manager import is_bed_slinger

    gcode_distance = -distance if is_bed_slinger(printer.model) else distance

    lines = []
    if force:
        lines.append("M211 S0")
    lines += ["G91", f"G1 Z{gcode_distance:.2f} F600", "G90"]
    if force:
        lines.append("M211 S1")

    if not client.send_gcode("\n".join(lines)):
        raise HTTPException(500, "Failed to send bed-jog command")

    return {"success": True, "message": f"Bed jog {distance:+.1f} mm sent"}


@router.post("/{printer_id}/xy-jog")
async def xy_jog(
    printer_id: int,
    x: float = Query(0, description="Signed relative X movement in mm"),
    y: float = Query(0, description="Signed relative Y movement in mm"),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Move the toolhead by a relative X/Y distance."""
    if (x == 0 and y == 0) or abs(x) > 200 or abs(y) > 200:
        raise HTTPException(400, "X/Y movement must be non-zero and ≤ 200 mm per axis")

    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    axes = []
    if x:
        axes.append(f"X{x:.2f}")
    if y:
        axes.append(f"Y{y:.2f}")

    if not client.send_gcode("\n".join(["G91", f"G1 {' '.join(axes)} F6000", "G90"])):
        raise HTTPException(500, "Failed to send XY jog command")

    return {"success": True, "message": f"XY jog X{x:+.1f} Y{y:+.1f} mm sent"}


@router.post("/{printer_id}/extruder-jog")
async def extruder_jog(
    printer_id: int,
    distance: float = Query(
        ..., description="Signed relative extrusion distance in mm. Positive extrudes, negative retracts."
    ),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Extrude or retract filament by a relative distance.

    No client-side cold-extrude guard: Bambu firmware refuses extrusion
    below its min-extrude temperature, so a cold call is rejected at the
    printer, not silently damaging the extruder gear.
    """
    if distance == 0 or abs(distance) > 100:
        raise HTTPException(400, "Extruder movement must be non-zero and ≤ 100 mm")

    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    if not client.send_gcode("\n".join(["M83", f"G1 E{distance:.2f} F300", "M82"])):
        raise HTTPException(500, "Failed to send extruder jog command")

    return {"success": True, "message": f"Extruder jog {distance:+.1f} mm sent"}


@router.post("/{printer_id}/home-axes")
async def home_axes(
    printer_id: int,
    axes: str = Query(
        "all",
        description="Legacy; accepted values are 'z' | 'xy' | 'all'. Always runs the printer's full auto-home sequence — see below.",
    ),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Run the printer's full auto-home sequence via bare `G28`.

    Bambu printers (H2C / H2D / H2S / X1 family) home the Z axis by moving
    the BED UP toward an endstop at the top of travel. If the toolhead is
    not already parked out of the way, a bare `G28 Z` will crash the bed
    into the toolhead — #1052 reported exactly that on H2C: the bed rose
    without stopping at a safe height because `G28 Z` skipped the
    toolhead-park step that a full `G28` runs first.

    The endpoint therefore ignores the `axes` argument and always sends a
    bare `G28`, which the firmware expands into a safe multi-step sequence
    (park toolhead → home XY → home Z). The argument is kept only for
    backward-compat with existing clients; sending an invalid value still
    returns 400 so typos surface instead of silently proceeding.
    """
    axes = axes.lower()
    if axes not in ("z", "xy", "all"):
        raise HTTPException(400, "axes must be 'z', 'xy', or 'all'")

    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    if not client.send_gcode("G28"):
        raise HTTPException(500, "Failed to send home command")

    return {"success": True, "message": "Full auto-home sequence sent"}


@router.post("/{printer_id}/hms/clear")
async def clear_hms_errors(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Clear HMS/print errors on the printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    success = client.clear_hms_errors()
    if not success:
        raise HTTPException(500, "Failed to clear HMS errors")

    return {"success": True, "message": "HMS errors cleared"}


@router.get("/{printer_id}/print/objects")
async def get_printable_objects(
    printer_id: int,
    reload: bool = False,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Get the list of printable objects for the current print.

    Returns a list of objects with id, name, position (if available), and skip status.
    Objects that have already been skipped are marked in the skipped_objects list.

    Args:
        reload: If True, reload objects from the archive file (useful after restart)
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    # Reload objects from 3MF if requested or no objects loaded
    if reload or not client.state.printable_objects:
        subtask_name = client.state.subtask_name
        if subtask_name:
            from backend.app.services.archive import extract_printable_objects_from_3mf
            from backend.app.services.bambu_ftp import download_file_try_paths_async

            # Build possible 3MF filenames (try both .gcode.3mf and .3mf)
            possible_filenames = []
            if subtask_name.endswith(".3mf"):
                possible_filenames.append(subtask_name)
            else:
                possible_filenames.append(f"{subtask_name}.gcode.3mf")
                possible_filenames.append(f"{subtask_name}.3mf")

            # Also try with spaces converted to underscores (Bambu Studio may normalize filenames)
            if " " in subtask_name:
                normalized = subtask_name.replace(" ", "_")
                if normalized.endswith(".3mf"):
                    possible_filenames.append(normalized)
                else:
                    possible_filenames.append(f"{normalized}.gcode.3mf")
                    possible_filenames.append(f"{normalized}.3mf")

            # Download 3MF from printer
            temp_path = settings.archive_dir / "temp" / f"objects_{printer_id}_{possible_filenames[0]}"
            temp_path.parent.mkdir(parents=True, exist_ok=True)

            # Build list of all remote paths to try
            remote_paths = []
            for filename in possible_filenames:
                remote_paths.extend([f"/{filename}", f"/cache/{filename}", f"/model/{filename}"])

            try:
                downloaded = await download_file_try_paths_async(
                    printer.ip_address,
                    printer.access_code,
                    remote_paths,
                    temp_path,
                    printer_model=printer.model,
                )
                if downloaded and temp_path.exists():
                    with open(temp_path, "rb") as f:
                        data = f.read()
                    objects, bbox_all = extract_printable_objects_from_3mf(
                        data,
                        plate_number=resolve_plate_id(client.state),
                        include_positions=True,
                    )
                    if objects:
                        client.state.printable_objects = objects
                        client.state.printable_objects_bbox_all = bbox_all
                        logger.info("Reloaded %s objects for printer %s", len(objects), printer_id)
            except Exception as e:
                logger.debug("Failed to reload objects from printer: %s", e)
            finally:
                if temp_path.exists():
                    temp_path.unlink()

    # Return objects with their skip status and position data
    objects = []
    for obj_id, obj_data in client.state.printable_objects.items():
        # Handle both old format (string name) and new format (dict with name, x, y)
        if isinstance(obj_data, dict):
            obj_entry = {
                "id": obj_id,
                "name": obj_data.get("name", f"Object {obj_id}"),
                "x": obj_data.get("x"),
                "y": obj_data.get("y"),
                "skipped": obj_id in client.state.skipped_objects,
            }
        else:
            # Legacy format: obj_data is just the name string
            obj_entry = {
                "id": obj_id,
                "name": obj_data,
                "x": None,
                "y": None,
                "skipped": obj_id in client.state.skipped_objects,
            }
        objects.append(obj_entry)

    return {
        "objects": objects,
        "total": len(objects),
        "skipped_count": len(client.state.skipped_objects),
        "is_printing": client.state.state in ("RUNNING", "PAUSE"),
        "bbox_all": getattr(client.state, "printable_objects_bbox_all", None),
    }


@router.post("/{printer_id}/print/skip-objects")
async def skip_objects(
    printer_id: int,
    object_ids: list[int],
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Skip specific objects during the current print.

    Args:
        object_ids: List of object identify_id values to skip
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    if not object_ids:
        raise HTTPException(400, "No object IDs provided")

    # Validate object IDs exist in printable_objects
    invalid_ids = [oid for oid in object_ids if oid not in client.state.printable_objects]
    if invalid_ids:
        raise HTTPException(400, f"Invalid object IDs: {invalid_ids}")

    success = client.skip_objects(object_ids)
    if not success:
        raise HTTPException(500, "Failed to skip objects")

    # Get names of skipped objects for response (handle both old and new format)
    skipped_names = []
    for oid in object_ids:
        obj_data = client.state.printable_objects.get(oid, str(oid))
        if isinstance(obj_data, dict):
            skipped_names.append(obj_data.get("name", str(oid)))
        else:
            skipped_names.append(obj_data)

    return {
        "success": True,
        "message": f"Skipped {len(object_ids)} object(s): {', '.join(skipped_names)}",
        "skipped_objects": object_ids,
    }


@router.get("/{printer_id}/runtime-debug")
async def get_runtime_debug(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Debug endpoint: Get runtime tracking status for a printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    state = printer_manager.get_status(printer_id)

    return {
        "printer_name": printer.name,
        "runtime_seconds": printer.runtime_seconds,
        "runtime_hours": printer.runtime_seconds / 3600.0 if printer.runtime_seconds else 0,
        "print_hours_offset": printer.print_hours_offset,
        "total_hours": (printer.runtime_seconds / 3600.0 if printer.runtime_seconds else 0)
        + (printer.print_hours_offset or 0),
        "last_runtime_update": printer.last_runtime_update.isoformat() if printer.last_runtime_update else None,
        "mqtt_state": {
            "connected": state.connected if state else False,
            "state": state.state if state else None,
            "progress": state.progress if state else None,
            "gcode_file": state.gcode_file if state else None,
        }
        if state
        else None,
        "is_active": printer.is_active,
    }


@router.post("/{printer_id}/hms/execute-action")
async def execute_hms_action(
    printer_id: int,
    body: HmsActionBody,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Execute an HMS action on the printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    # Snapshot pre-state so we can verify the printer actually acted on the
    # command. publish() success is NOT the same as printer-ack: Bambu's
    # firmware silently rejects malformed HMS commands at QoS 1 (the broker
    # ACKs the publish, but the printer drops it). Verified end-to-end against
    # a live H2D — see #1830 §(3).
    #
    # We probe `_last_message_time` (bumped on every MQTT push) rather than a
    # (gcode_state, hms_errors-length) diff. The old diff missed the
    # wrong-plate IGNORE_RESUME case where the printer briefly resumes and
    # re-pauses with the same fault inside the 2.5s window: both fields
    # round-trip to their pre-publish values → false 502 even though the
    # firmware fully ack'd the resume. Every accepted command triggers a
    # pushall response within ~100-500ms, so a fresh inbound message after
    # the publish is the robust ack signal.
    pre_last_message = client._last_message_time

    success = client.execute_hms_action(body.print_error, body.action, body.job_id)
    if not success:
        raise HTTPException(400, "Failed to execute HMS action")

    # Give the printer time to push a state update. The dispatch helper already
    # publishes a pushall after every command, so a fresh status should arrive
    # within ~1s; the default 2.5s covers slower firmware variants without
    # making the UI feel hung. Plain sleep is fine — paho's MQTT callback
    # runs in its own thread and updates state regardless of whether this
    # coroutine is awaiting.
    await asyncio.sleep(_hms_action_ack_wait_seconds())

    acked = client._last_message_time > pre_last_message
    if not acked:
        # Publish succeeded but the printer sent nothing back. Almost always
        # firmware-side silent rejection (err mismatch, command/state mismatch)
        # or a dropped MQTT route. 502 makes it visible at the UI instead of
        # the 200-but-broken loop #1830 reported.
        raise HTTPException(502, "Printer did not acknowledge HMS action within 2.5s")

    return {"success": True, "message": "HMS action executed"}
