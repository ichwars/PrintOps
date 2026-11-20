import logging

from backend.app.core.database import async_session
from backend.app.core.websocket import ws_manager
from backend.app.models.printer import Printer
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.bambu_mqtt import PrinterState
from backend.app.services.inventory_mode import spoolman_owns_assignments
from backend.app.services.notification_service import notification_service
from backend.app.services.printer_manager import printer_manager, printer_tray_layout
from backend.app.utils.tray_ids import (
    EXTERNAL_DEPUTY_ID,
    RACK_EXTERNAL_IDS,
    AmsType,
    TrayLayout,
    decode_wire_slot,
    external_hotend,
)


def _global_tray_from_assignment(ams_id: int, tray_id: int, layout: TrayLayout | None = None) -> int:
    """Convert an assignment tuple to PrintOps global tray ID."""
    if ams_id == EXTERNAL_DEPUTY_ID:
        # Older records keep the left external spool as its own ams_id.
        return EXTERNAL_DEPUTY_ID + tray_id
    return (layout or TrayLayout()).tray_from_slot_key(ams_id, tray_id)


def _slot_label_from_global_tray(global_tray_id: int, layout: TrayLayout | None = None) -> str:
    """Return a human-readable slot label from a global tray ID."""
    layout = layout or TrayLayout()
    if (layout.rack and layout.is_external(global_tray_id)) or (
        RACK_EXTERNAL_IDS.start <= global_tray_id < EXTERNAL_DEPUTY_ID
    ):
        # One external input per hotend, numbered like Bambu Studio's "Ext-n".
        # 247-253 are only ever such inputs, so they read so without a layout.
        return f"Ext-{external_hotend(global_tray_id) + 1}"
    if global_tray_id == 254:
        return "Ext-L"
    if global_tray_id == 255:
        return "Ext-R"
    if global_tray_id >= 128:
        return f"HT-{chr(65 + (global_tray_id - 128))}"
    ams_id, tray_id = layout.slot_key(global_tray_id)
    kind = layout.ams_type(ams_id)
    if kind == AmsType.ZMULTI_A:
        return f"3H-{tray_id + 1}"
    if kind == AmsType.ZMULTI_B:
        return f"B-{tray_id + 1}"
    return f"{chr(65 + ams_id)}{tray_id + 1}"


def _tray_profile_and_color_for_global_id(state: PrinterState | None, global_tray_id: int) -> tuple[str, str]:
    """Resolve expected tray material/profile and color for a global tray ID from current printer state."""
    if not state or not state.raw_data:
        return ("Unknown", "Unknown")

    ams_raw = state.raw_data.get("ams", {})
    ams_units = ams_raw.get("ams", []) if isinstance(ams_raw, dict) else ams_raw if isinstance(ams_raw, list) else []
    layout = TrayLayout.from_state(state)

    vt_trays = state.raw_data.get("vt_tray", [])
    if not isinstance(vt_trays, list):
        vt_trays = []

    for tray in vt_trays:
        if not isinstance(tray, dict):
            continue
        if int(tray.get("id", -1)) == global_tray_id:
            profile = tray.get("tray_sub_brands") or tray.get("tray_type") or "Unknown"
            color = tray.get("tray_color") or "Unknown"
            return (profile, color)

    for ams in ams_units:
        if not isinstance(ams, dict):
            continue
        ams_id = int(ams.get("id", -1))
        trays = ams.get("tray", [])
        if not isinstance(trays, list):
            continue
        for tray in trays:
            if not isinstance(tray, dict):
                continue
            tray_id = int(tray.get("id", -1))
            if layout.global_tray_id(ams_id, tray_id) == global_tray_id:
                profile = tray.get("tray_sub_brands") or tray.get("tray_type") or "Unknown"
                color = tray.get("tray_color") or "Unknown"
                return (profile, color)

    return ("Unknown", "Unknown")


def _decode_mqtt_mapping_to_global_trays(mapping_raw: object, layout: TrayLayout | None = None) -> list[int]:
    """Decode printer MQTT mapping values into PrintOps global tray IDs."""
    if not isinstance(mapping_raw, list) or not mapping_raw:
        return []

    decoded = (decode_wire_slot(value, layout) for value in mapping_raw)
    return [tray for tray in decoded if tray is not None]


async def notify_missing_spool_assignments_on_print_start(
    printer_id: int,
    data: dict,
    logger: logging.Logger,
) -> None:
    """Send notification when print-start mapping references unassigned trays."""
    explicit_mapping = data.get("ams_mapping")
    explicit_values = (
        [value for value in explicit_mapping if isinstance(value, int)] if isinstance(explicit_mapping, list) else []
    )
    raw_mapping = data.get("raw_data", {}).get("mapping") if isinstance(data.get("raw_data"), dict) else None
    layout = printer_tray_layout(printer_id, printer_manager)
    decoded_values = _decode_mqtt_mapping_to_global_trays(raw_mapping, layout)
    mapping_values = explicit_values if explicit_values else decoded_values

    used_global_trays = {value for value in mapping_values if value >= 0}
    if not used_global_trays:
        return

    try:
        async with async_session() as db:
            printer = await db.get(Printer, printer_id)
            printer_name = printer.name if printer else f"Printer {printer_id}"

            table = SpoolmanSlotAssignment if await spoolman_owns_assignments(db) else SpoolAssignment
            rows = (await db.execute(table.__table__.select().where(table.printer_id == printer_id))).fetchall()
            assigned_global_trays = {_global_tray_from_assignment(row.ams_id, row.tray_id, layout) for row in rows}

            missing_global = sorted(used_global_trays - assigned_global_trays)
            if not missing_global:
                return

            await _send_missing_assignment_notification(printer_id, printer_name, missing_global, db)
    except Exception as e:
        logger.warning("Missing spool-assignment notification failed: %s", e)


async def _send_missing_assignment_notification(printer_id: int, printer_name: str, missing: list[int], db) -> None:
    state = printer_manager.get_status(printer_id)
    layout = TrayLayout.from_state(state)
    missing_slots = []
    for global_id in missing:
        profile, color = _tray_profile_and_color_for_global_id(state, global_id)
        missing_slots.append(
            {"slot": _slot_label_from_global_tray(global_id, layout), "profile": profile, "color": color}
        )
    await ws_manager.send_missing_spool_assignment(
        printer_id=printer_id,
        printer_name=printer_name,
        missing_slots=missing_slots,
    )
    await notification_service.on_print_missing_spool_assignment(
        printer_id=printer_id,
        printer_name=printer_name,
        missing_slots=missing_slots,
        db=db,
    )


async def notify_missing_spool_assignments_on_print_complete(
    printer_id: int,
    missing_global_trays: list[int],
    db,
    logger: logging.Logger,
) -> None:
    """Surface realized internal-inventory usage that could not be booked."""
    if not missing_global_trays:
        return
    try:
        printer = await db.get(Printer, printer_id)
        printer_name = printer.name if printer else f"Printer {printer_id}"
        await _send_missing_assignment_notification(
            printer_id,
            printer_name,
            sorted(set(missing_global_trays)),
            db,
        )
    except Exception as exc:  # noqa: BLE001 - notifications cannot fail completion
        logger.warning("Missing spool-assignment completion notification failed: %s", exc)
