import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    RequirePermissionIfAuthEnabled,
)
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.core.tasks import spawn_background_task
from backend.app.models.ams_label import AmsLabel
from backend.app.models.printer import Printer
from backend.app.models.slot_preset import SlotPresetMapping
from backend.app.schemas.printer import (
    AmsLabelBody,
)
from backend.app.utils.filament_ids import filament_id_to_setting_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["printers"])


class _PrinterManagerProxy:
    def __getattr__(self, name: str):
        from backend.app.api.routes import printers as printers_routes

        return getattr(printers_routes.printer_manager, name)


printer_manager = _PrinterManagerProxy()


@router.post("/{printer_id}/slots/{ams_id}/{tray_id}/configure")
async def configure_ams_slot(
    printer_id: int,
    ams_id: int,
    tray_id: int,
    tray_info_idx: str = Query(...),
    tray_type: str = Query(...),
    tray_sub_brands: str = Query(...),
    tray_color: str = Query(...),
    nozzle_temp_min: int = Query(...),
    nozzle_temp_max: int = Query(...),
    cali_idx: int = Query(-1),
    nozzle_diameter: str = Query("0.4"),
    setting_id: str = Query(""),
    kprofile_filament_id: str = Query(""),
    kprofile_setting_id: str = Query(""),
    k_value: float = Query(0.0),
    db: AsyncSession = Depends(get_db),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
):
    """Configure an AMS slot with a specific filament setting and K profile.

    This sends two commands to the printer:
    1. ams_filament_setting - sets filament type, color, temperature
    2. extrusion_cali_sel - sets the K profile (pressure advance value)

    Args:
        printer_id: Database ID of the printer
        ams_id: AMS unit ID (0-3 for regular AMS, 128-135 for HT AMS)
        tray_id: Tray ID within the AMS (0-3)
        tray_info_idx: Filament ID short format (e.g., "GFL05") or user preset ID
        tray_type: Filament type (e.g., "PLA", "PETG")
        tray_sub_brands: Sub-brand/profile name (e.g., "PLA Basic", "PETG HF")
        tray_color: Color in RRGGBBAA hex format (e.g., "FFFF00FF")
        nozzle_temp_min: Minimum nozzle temperature
        nozzle_temp_max: Maximum nozzle temperature
        cali_idx: K profile calibration index (-1 for default 0.020)
        nozzle_diameter: Nozzle diameter string (e.g., "0.4")
        setting_id: Full setting ID with version (e.g., "GFSL05_07") - optional
        kprofile_filament_id: K profile's filament_id for proper K profile linking
        k_value: Direct K value to set (0.0 to skip direct K value setting)
    """
    logger = logging.getLogger(__name__)
    logger.info("[configure_ams_slot] printer_id=%s, ams_id=%s, tray_id=%s", printer_id, ams_id, tray_id)
    logger.info(
        f"[configure_ams_slot] tray_info_idx={tray_info_idx!r}, tray_type={tray_type!r}, tray_sub_brands={tray_sub_brands!r}"
    )
    logger.info(
        f"[configure_ams_slot] setting_id={setting_id!r}, kprofile_filament_id={kprofile_filament_id!r}, kprofile_setting_id={kprofile_setting_id!r}"
    )

    # Get MQTT client for this printer
    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(status_code=400, detail="Printer not connected")

    # Resolve tray_info_idx for the MQTT command.
    # Priority:
    #   1. Use the provided tray_info_idx if set (including cloud-synced
    #      custom presets like PFUS* / P*).
    #   2. Reuse the slot's existing tray_info_idx if it's a specific
    #      (non-generic) preset for the same material.
    #   3. Fall back to a generic Bambu filament ID.
    _GENERIC_FILAMENT_IDS = {
        "PLA": "GFL99",
        "PETG": "GFG99",
        "ABS": "GFB99",
        "ASA": "GFB98",
        "PC": "GFC99",
        "PA": "GFN99",
        "NYLON": "GFN99",
        "TPU": "GFU99",
        "PVA": "GFS99",
        "HIPS": "GFS98",
        "PLA-CF": "GFL98",
        "PETG-CF": "GFG98",
        "PA-CF": "GFN98",
        "PETG HF": "GFG96",
    }
    _GENERIC_ID_VALUES = set(_GENERIC_FILAMENT_IDS.values())
    effective_tray_info_idx = tray_info_idx

    if not tray_info_idx:
        # No preset provided — try slot reuse or generic fallback
        current_tray_info_idx = ""
        current_tray_type = ""
        state = printer_manager.get_status(printer_id)
        if state and state.raw_data:
            from backend.app.api.routes.inventory import _find_tray_in_ams_data

            if ams_id == 255:
                vt_tray = state.raw_data.get("vt_tray") or []
                ext_id = tray_id + 254
                for vt in vt_tray:
                    if isinstance(vt, dict) and int(vt.get("id", 254)) == ext_id:
                        current_tray_info_idx = vt.get("tray_info_idx", "")
                        current_tray_type = vt.get("tray_type", "")
                        break
            else:
                ams_data = state.raw_data.get("ams", {})
                ams_list = (
                    ams_data.get("ams", [])
                    if isinstance(ams_data, dict)
                    else ams_data
                    if isinstance(ams_data, list)
                    else []
                )
                cur_tray = _find_tray_in_ams_data(ams_list, ams_id, tray_id)
                if cur_tray:
                    current_tray_info_idx = cur_tray.get("tray_info_idx", "")
                    current_tray_type = cur_tray.get("tray_type", "")

        if (
            current_tray_info_idx
            and current_tray_info_idx not in _GENERIC_ID_VALUES
            and current_tray_type
            and current_tray_type.upper() == tray_type.upper()
        ):
            logger.info(
                "[configure_ams_slot] Reusing slot's existing tray_info_idx=%r (same material %r)",
                current_tray_info_idx,
                tray_type,
            )
            effective_tray_info_idx = current_tray_info_idx
        elif tray_type:
            material = tray_type.upper().strip()
            generic = (
                _GENERIC_FILAMENT_IDS.get(material)
                or _GENERIC_FILAMENT_IDS.get(material.split("-")[0].split(" ")[0])
                or ""
            )
            if generic:
                logger.info("[configure_ams_slot] Falling back to generic %r for material %r", generic, tray_type)
                effective_tray_info_idx = generic

    # Send filament setting + K-profile commands
    filament_id_for_kprofile = kprofile_filament_id if kprofile_filament_id else effective_tray_info_idx

    # Realign the slot's filament context to the K-profile's calibration
    # context. The printer's calibration table is keyed by (filament_id,
    # cali_idx) — so for the cali_idx selected via extrusion_cali_sel to
    # actually stick to the slot, ams_filament_setting must declare the
    # slot under the SAME filament_id.
    #
    # Without this, configure_ams_slot would send:
    #   ams_filament_setting → tray_info_idx=GFL99 (generic from material)
    #   extrusion_cali_sel    → filament_id=P4d64437 (kp's preset)
    # ...and the cali_idx would silently be dropped to default because the
    # slot's filament context (GFL99) doesn't match the kp's (P4d64437).
    #
    # This realignment fires only when the kp is targeted at a different
    # preset than the user's filament selection AND the kp's preset is a
    # valid tray_info_idx (GF* official, P* local — not PFUS* cloud-user
    # which the slicer rejects in tray_info_idx).
    effective_setting_id = setting_id
    if (
        kprofile_filament_id
        and kprofile_filament_id != effective_tray_info_idx
        and not kprofile_filament_id.startswith("PFUS")
    ):
        logger.info(
            "[configure_ams_slot] realigning slot filament context to kp: tray_info_idx %r → %r, setting_id %r → %r",
            effective_tray_info_idx,
            kprofile_filament_id,
            setting_id,
            kprofile_setting_id or setting_id,
        )
        effective_tray_info_idx = kprofile_filament_id
        if kprofile_setting_id:
            effective_setting_id = kprofile_setting_id

    if effective_tray_info_idx and not effective_setting_id:
        effective_setting_id = filament_id_to_setting_id(effective_tray_info_idx)

    # Always send ams_set_filament_setting — the user explicitly clicked
    # "Configure Slot", so honor that.  Previous versions skipped this for
    # RFID-tagged slots to preserve the slicer eye icon, but printers cache
    # stale tag_uid/tray_uuid after a BL spool is removed, causing the check
    # to false-positive on non-RFID slots and silently drop the command.
    success = client.ams_set_filament_setting(
        ams_id=ams_id,
        tray_id=tray_id,
        tray_info_idx=effective_tray_info_idx,
        tray_type=tray_type,
        tray_sub_brands=tray_sub_brands,
        tray_color=tray_color,
        nozzle_temp_min=nozzle_temp_min,
        nozzle_temp_max=nozzle_temp_max,
        setting_id=effective_setting_id,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send filament configuration command")

    # Method 1: Select existing calibration profile by cali_idx
    # Do NOT include setting_id — BambuStudio never sends it in extrusion_cali_sel,
    # and including it causes the firmware to mislink the profile on X1C/P1S.
    client.extrusion_cali_sel(
        ams_id=ams_id,
        tray_id=tray_id,
        cali_idx=cali_idx,
        filament_id=filament_id_for_kprofile,
        nozzle_diameter=nozzle_diameter,
    )

    # Method 2: Only send extrusion_cali_set when NO existing profile was selected
    # (cali_idx == -1). When cali_idx >= 0, extrusion_cali_sel already selected the
    # correct profile. Sending extrusion_cali_set with the same cali_idx would MODIFY
    # the existing profile's metadata (extruder_id, nozzle_id, name, setting_id),
    # corrupting it — e.g., overwriting a High Flow extruder 1 profile with
    # hardcoded extruder_id=0 and nozzle_id=HS00.
    if k_value > 0 and cali_idx < 0:
        # Calculate global tray ID for extrusion_cali_set
        if ams_id <= 3:
            global_tray_id = ams_id * 4 + tray_id
        elif ams_id >= 128 and ams_id <= 135:
            global_tray_id = (ams_id - 128) * 4 + tray_id
        else:
            global_tray_id = tray_id

        client.extrusion_cali_set(
            tray_id=global_tray_id,
            k_value=k_value,
            nozzle_diameter=nozzle_diameter,
            nozzle_temp=nozzle_temp_max,
            filament_id=filament_id_for_kprofile,
            setting_id=kprofile_setting_id or "",
            name=tray_sub_brands or "",
            cali_idx=cali_idx,
        )

    # Persist the user's K-profile choice so it survives RFID re-reads and
    # session restarts. Pre-Phase-13 this was ephemeral — the MQTT command
    # took effect on the printer but printops never recorded it, so the next
    # `_apply_pa_after_refresh` cycle had no stored profile to re-assert.
    if cali_idx >= 0:
        try:
            from sqlalchemy.orm import selectinload

            from backend.app.models.spool_assignment import SpoolAssignment
            from backend.app.models.spool_k_profile import SpoolKProfile
            from backend.app.models.spoolman_k_profile import SpoolmanKProfile
            from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment

            # Resolve slot's extruder index for the K-profile match key. Same
            # logic as _apply_pa_after_refresh: external slots invert tray→extruder,
            # AMS slots come from ams_extruder_map. Falls back to 0 (single-nozzle).
            slot_state = printer_manager.get_status(printer_id)
            slot_extruder: int | None = None
            if slot_state and slot_state.ams_extruder_map:
                if ams_id == 255:
                    slot_extruder = 1 - tray_id
                else:
                    slot_extruder = slot_state.ams_extruder_map.get(str(ams_id))
            kp_extruder = slot_extruder if slot_extruder is not None else 0

            # Spoolman SlotAssignment first — has UniqueConstraint, idempotent.
            sm_result = await db.execute(
                select(SpoolmanSlotAssignment).where(
                    SpoolmanSlotAssignment.printer_id == printer_id,
                    SpoolmanSlotAssignment.ams_id == ams_id,
                    SpoolmanSlotAssignment.tray_id == tray_id,
                )
            )
            sm_assignment = sm_result.scalar_one_or_none()
            if sm_assignment:
                existing = await db.execute(
                    select(SpoolmanKProfile).where(
                        SpoolmanKProfile.spoolman_spool_id == sm_assignment.spoolman_spool_id,
                        SpoolmanKProfile.printer_id == printer_id,
                        SpoolmanKProfile.extruder == kp_extruder,
                        SpoolmanKProfile.nozzle_diameter == nozzle_diameter,
                    )
                )
                kp = existing.scalar_one_or_none()
                if kp:
                    kp.cali_idx = cali_idx
                    kp.k_value = k_value or 0.0
                    kp.setting_id = kprofile_setting_id or None
                    kp.name = tray_sub_brands or None
                else:
                    db.add(
                        SpoolmanKProfile(
                            spoolman_spool_id=sm_assignment.spoolman_spool_id,
                            printer_id=printer_id,
                            extruder=kp_extruder,
                            nozzle_diameter=nozzle_diameter,
                            k_value=k_value or 0.0,
                            name=tray_sub_brands or None,
                            cali_idx=cali_idx,
                            setting_id=kprofile_setting_id or None,
                        )
                    )
                await db.commit()
                logger.info(
                    "[configure_ams_slot] Persisted Spoolman K-profile spool=%d printer=%d ams=%d tray=%d cali_idx=%d",
                    sm_assignment.spoolman_spool_id,
                    printer_id,
                    ams_id,
                    tray_id,
                    cali_idx,
                )
            else:
                # Local SpoolAssignment + SpoolKProfile (no UNIQUE — use .first())
                local_result = await db.execute(
                    select(SpoolAssignment)
                    .options(selectinload(SpoolAssignment.spool))
                    .where(
                        SpoolAssignment.printer_id == printer_id,
                        SpoolAssignment.ams_id == ams_id,
                        SpoolAssignment.tray_id == tray_id,
                    )
                )
                local_assignment = local_result.scalar_one_or_none()
                if local_assignment and local_assignment.spool:
                    existing = await db.execute(
                        select(SpoolKProfile).where(
                            SpoolKProfile.spool_id == local_assignment.spool.id,
                            SpoolKProfile.printer_id == printer_id,
                            SpoolKProfile.extruder == kp_extruder,
                            SpoolKProfile.nozzle_diameter == nozzle_diameter,
                        )
                    )
                    # SpoolKProfile has no unique constraint on this tuple, so
                    # multiple rows could theoretically exist (shouldn't, but
                    # don't crash if they do). Update the first match, leave
                    # any duplicates alone.
                    kp = existing.scalars().first()
                    if kp:
                        kp.cali_idx = cali_idx
                        kp.k_value = k_value or 0.0
                        kp.setting_id = kprofile_setting_id or None
                        kp.name = tray_sub_brands or None
                    else:
                        db.add(
                            SpoolKProfile(
                                spool_id=local_assignment.spool.id,
                                printer_id=printer_id,
                                extruder=kp_extruder,
                                nozzle_diameter=nozzle_diameter,
                                k_value=k_value or 0.0,
                                name=tray_sub_brands or None,
                                cali_idx=cali_idx,
                                setting_id=kprofile_setting_id or None,
                            )
                        )
                    await db.commit()
                    logger.info(
                        "[configure_ams_slot] Persisted local K-profile spool=%d printer=%d ams=%d tray=%d cali_idx=%d",
                        local_assignment.spool.id,
                        printer_id,
                        ams_id,
                        tray_id,
                        cali_idx,
                    )
        except Exception:
            # MQTT command was already sent successfully — DB persist is best-effort.
            logger.exception(
                "[configure_ams_slot] Failed to persist K-profile (printer=%d ams=%d tray=%d cali_idx=%d)",
                printer_id,
                ams_id,
                tray_id,
                cali_idx,
            )
            try:
                await db.rollback()
            except Exception:
                pass

    # Request fresh status push from printer so frontend gets updated data via WebSocket
    logger.info("[configure_ams_slot] Requesting status update from printer")
    update_result = client.request_status_update()
    logger.info("[configure_ams_slot] Status update request result: %s", update_result)

    return {
        "success": True,
        "message": f"Configured AMS {ams_id} tray {tray_id} with {tray_sub_brands}",
    }


@router.post("/{printer_id}/ams/{ams_id}/tray/{tray_id}/reset")
async def reset_ams_slot(
    printer_id: int,
    ams_id: int,
    tray_id: int,
    db: AsyncSession = Depends(get_db),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
):
    """Reset an AMS slot to empty/unconfigured state.

    This clears the filament configuration from the slot.
    """
    # Get MQTT client for this printer
    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(status_code=400, detail="Printer not connected")

    # Reset the slot
    success = client.reset_ams_slot(ams_id=ams_id, tray_id=tray_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send reset command")

    # Also delete any saved slot preset mapping
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

    # Request fresh status push from printer so frontend gets updated data via WebSocket
    client.request_status_update()

    return {
        "success": True,
        "message": f"Reset AMS {ams_id} tray {tray_id}",
    }


@router.get("/{printer_id}/ams-labels")
async def get_ams_labels(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Get all user-defined AMS labels for a printer, keyed by AMS unit ID.

    Labels are stored by AMS serial number.  This endpoint resolves the current
    serial-to-ams_id mapping from the live printer state so the response is still
    keyed by ams_id for UI compatibility.
    """
    # Build serial -> ams_id map from live printer state
    serial_to_ams_id: dict[str, int] = {}
    state = printer_manager.get_status(printer_id)
    if state and state.raw_data:
        for ams_unit in state.raw_data.get("ams", []):
            sn = str(ams_unit.get("sn") or ams_unit.get("serial_number") or "")
            if sn:
                serial_to_ams_id[sn] = int(ams_unit.get("id", 0))

    # Collect all known serials for this printer (live + synthetic fallback keys)
    serials_to_query = set(serial_to_ams_id.keys())

    # Fetch labels for all known serials
    labels: dict[int, str] = {}
    if serials_to_query:
        result = await db.execute(select(AmsLabel).where(AmsLabel.ams_serial_number.in_(serials_to_query)))
        for lbl in result.scalars().all():
            aid = serial_to_ams_id.get(lbl.ams_serial_number)
            if aid is not None:
                labels[aid] = lbl.label

    # Also fetch labels stored under synthetic keys for this printer (backward compat)
    # Collect all synthetic keys first, then query with a single IN clause.
    if state and state.raw_data:
        synthetic_key_to_aid: dict[str, int] = {
            f"p{printer_id}a{int(ams_unit.get('id', 0))}": int(ams_unit.get("id", 0))
            for ams_unit in state.raw_data.get("ams", [])
            if int(ams_unit.get("id", 0)) not in labels
        }
        if synthetic_key_to_aid:
            result = await db.execute(
                select(AmsLabel).where(AmsLabel.ams_serial_number.in_(synthetic_key_to_aid.keys()))
            )
            for lbl in result.scalars().all():
                aid = synthetic_key_to_aid.get(lbl.ams_serial_number)
                if aid is not None:
                    labels[aid] = lbl.label

    return labels


@router.put("/{printer_id}/ams-labels/{ams_id}")
async def save_ams_label(
    printer_id: int,
    ams_id: int,
    body: AmsLabelBody,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the friendly name for a specific AMS unit.

    When ``ams_serial`` is provided the label is stored under that serial number so
    it survives the AMS being moved to a different printer.  When it is absent (e.g.
    older firmware that does not report a serial) a synthetic key based on the
    printer_id and ams_id is used as a fallback.
    """
    # Verify printer exists
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Printer not found")

    # Determine the serial key to store under
    stripped = body.ams_serial.strip() if body.ams_serial else ""
    serial_key = stripped if stripped else f"p{printer_id}a{ams_id}"

    result = await db.execute(select(AmsLabel).where(AmsLabel.ams_serial_number == serial_key))
    existing = result.scalar_one_or_none()

    if existing:
        existing.label = body.label
        existing.ams_id = ams_id
    else:
        db.add(AmsLabel(ams_serial_number=serial_key, ams_id=ams_id, label=body.label))

    await db.commit()
    return {"ams_id": ams_id, "label": body.label}


@router.delete("/{printer_id}/ams-labels/{ams_id}")
async def delete_ams_label(
    printer_id: int,
    ams_id: int,
    ams_serial: str = Query(default="", max_length=50),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
    db: AsyncSession = Depends(get_db),
):
    """Delete the friendly name for a specific AMS unit, reverting to the auto label."""
    stripped = ams_serial.strip() if ams_serial else ""
    serial_key = stripped if stripped else f"p{printer_id}a{ams_id}"

    result = await db.execute(select(AmsLabel).where(AmsLabel.ams_serial_number == serial_key))
    existing = result.scalar_one_or_none()

    if existing:
        await db.delete(existing)
        await db.commit()

    return {"success": True}


@router.post("/{printer_id}/ams/{ams_id}/slot/{slot_id}/refresh")
async def refresh_ams_slot(
    printer_id: int,
    ams_id: int,
    slot_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_AMS_RFID),
    db: AsyncSession = Depends(get_db),
):
    """Re-read RFID for an AMS slot (triggers filament info refresh)."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    success, message = client.ams_refresh_tray(ams_id, slot_id)
    if not success:
        raise HTTPException(400, message)

    # Apply PA profile after delay (RFID re-read takes a few seconds)
    spawn_background_task(
        _apply_pa_after_refresh(printer_id, ams_id, slot_id),
        name=f"apply-pa-after-refresh-{printer_id}-{ams_id}-{slot_id}",
    )

    return {"success": True, "message": message}


async def _apply_pa_after_refresh(printer_id: int, ams_id: int, slot_id: int):
    """Apply PA profile after RFID re-read completes.

    Waits for the printer to finish processing the RFID data, then selects
    the K-profile via extrusion_cali_sel.  Does NOT re-send ams_set_filament_setting
    because that would overwrite the RFID-provided filament data.
    """
    # Keep legacy monkeypatches of backend.app.api.routes.printers.asyncio.sleep
    # effective even though this endpoint group now lives in its own module.
    from backend.app.api.routes import printers as printers_routes

    await printers_routes.asyncio.sleep(5)
    try:
        from backend.app.api.routes.inventory import _find_tray_in_ams_data
        from backend.app.core.database import async_session
        from backend.app.models.spool import Spool
        from backend.app.models.spool_assignment import SpoolAssignment as SA
        from backend.app.models.spoolman_k_profile import SpoolmanKProfile
        from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
        from backend.app.services.spool_tag_matcher import (
            ZERO_TAG_UID,
            ZERO_TRAY_UUID,
            is_bambu_tag,
        )
        from backend.app.utils.tag_normalization import (
            normalize_tag_uid,
            normalize_tray_uuid,
        )

        client = printer_manager.get_client(printer_id)
        if not client:
            return

        state = printer_manager.get_status(printer_id)
        if not state or not state.raw_data:
            return

        # Find current tray data (should have RFID data by now)
        ams_data = state.raw_data.get("ams", {})
        ams_list = (
            ams_data.get("ams", []) if isinstance(ams_data, dict) else ams_data if isinstance(ams_data, list) else []
        )
        tray = _find_tray_in_ams_data(ams_list, ams_id, slot_id)
        if not tray or not tray.get("tray_type"):
            logger.debug("PA re-apply: no tray data for AMS%d-T%d", ams_id, slot_id)
            return

        tag_uid = tray.get("tag_uid", "")
        tray_uuid = tray.get("tray_uuid", "")
        tray_info_idx = tray.get("tray_info_idx", "")
        if not is_bambu_tag(tag_uid, tray_uuid, tray_info_idx):
            return

        # Compute nozzle/extruder once — used by both local and Spoolman lookup.
        nozzle_diameter = "0.4"
        if state.nozzles:
            nd = state.nozzles[0].nozzle_diameter
            if nd:
                nozzle_diameter = nd

        slot_extruder = None
        if state.ams_extruder_map:
            if ams_id == 255:
                # External slots: ext-L (tray 0) → extruder 1, ext-R (tray 1) → extruder 0
                slot_extruder = 1 - slot_id
            else:
                slot_extruder = state.ams_extruder_map.get(str(ams_id))

        # 3-stage K-profile cascade: local SpoolKProfile → Spoolman SpoolmanKProfile
        # → live tray.cali_idx fallback. Pre-Phase-13 only handled the local path
        # and exited silently if no SpoolKProfile match; Spoolman-assigned slots
        # were ignored entirely and live cali_idx was never re-asserted.
        matching_cali_idx: int | None = None
        matching_filament_id: str = tray_info_idx

        async with async_session() as db:
            from sqlalchemy import or_, select as sa_select
            from sqlalchemy.orm import selectinload

            # Stage 1: local SpoolAssignment + SpoolKProfile match
            result = await db.execute(
                sa_select(SA)
                .options(selectinload(SA.spool).selectinload(Spool.k_profiles))
                .where(SA.printer_id == printer_id, SA.ams_id == ams_id, SA.tray_id == slot_id)
            )
            assignment = result.scalar_one_or_none()
            spool: Spool | None = assignment.spool if assignment else None

            # Stage 1b: tag-based fallback. The slot may have just been reset
            # (SpoolAssignment row deleted) before the user triggered a re-read.
            # The live tray already carries the spool's tray_uuid/tag_uid from
            # the RFID re-read, but the SA row hasn't been re-created yet.
            # Without this fallback we miss the stored SpoolKProfile and Stage 3
            # ends up re-asserting whatever cali_idx the firmware reset to
            # (typically the default profile).
            if spool is None:
                norm_uuid = normalize_tray_uuid(tray_uuid) if tray_uuid else ""
                norm_tag = normalize_tag_uid(tag_uid) if tag_uid else ""
                tag_filters = []
                if norm_uuid and norm_uuid != ZERO_TRAY_UUID:
                    tag_filters.append(Spool.tray_uuid == norm_uuid)
                if norm_tag and norm_tag != ZERO_TAG_UID:
                    tag_filters.append(Spool.tag_uid == norm_tag)
                if tag_filters:
                    tag_lookup = await db.execute(
                        sa_select(Spool).options(selectinload(Spool.k_profiles)).where(or_(*tag_filters)).limit(1)
                    )
                    spool = tag_lookup.scalar_one_or_none()
                    if spool is not None:
                        logger.info(
                            "PA re-apply AMS%d-T%d: matched spool %d via tag fallback "
                            "(SpoolAssignment row missing, likely after slot reset)",
                            ams_id,
                            slot_id,
                            spool.id,
                        )

            if spool is not None and spool.k_profiles:
                # Prefer exact extruder match, fall back to extruder-agnostic kp
                # for the same printer + nozzle. Hard-skipping on extruder
                # mismatch made the cascade refuse perfectly valid stored
                # profiles whenever the AMS-extruder mapping had shifted since
                # calibration time, falling all the way through to Stage 3 and
                # re-asserting the firmware default.
                exact_kp = None
                fallback_kp = None
                for kp in spool.k_profiles:
                    if kp.printer_id != printer_id or kp.nozzle_diameter != nozzle_diameter or kp.cali_idx is None:
                        continue
                    if slot_extruder is not None and kp.extruder is not None and kp.extruder == slot_extruder:
                        exact_kp = kp
                        break
                    if fallback_kp is None:
                        fallback_kp = kp
                chosen_kp = exact_kp or fallback_kp
                if chosen_kp is not None:
                    matching_cali_idx = chosen_kp.cali_idx
                    # The filament_id in extrusion_cali_sel must match the preset
                    # under which the K-profile was calibrated. Prefer the spool's
                    # slicer_filament setting, falling back to the tray's RFID value.
                    matching_filament_id = spool.slicer_filament or tray_info_idx

            # Stage 2: Spoolman SpoolmanSlotAssignment + SpoolmanKProfile match
            # (only when no local spool was matched — local takes priority,
            # including the tag-based fallback above)
            if matching_cali_idx is None and spool is None:
                sm_result = await db.execute(
                    sa_select(SpoolmanSlotAssignment).where(
                        SpoolmanSlotAssignment.printer_id == printer_id,
                        SpoolmanSlotAssignment.ams_id == ams_id,
                        SpoolmanSlotAssignment.tray_id == slot_id,
                    )
                )
                sm_assignment = sm_result.scalar_one_or_none()
                if sm_assignment:
                    kp_result = await db.execute(
                        sa_select(SpoolmanKProfile).where(
                            SpoolmanKProfile.spoolman_spool_id == sm_assignment.spoolman_spool_id,
                            SpoolmanKProfile.printer_id == printer_id,
                        )
                    )
                    for kp in kp_result.scalars().all():
                        if kp.nozzle_diameter == nozzle_diameter:
                            if slot_extruder is not None and kp.extruder is not None and kp.extruder != slot_extruder:
                                continue
                            if kp.cali_idx is not None:
                                matching_cali_idx = kp.cali_idx
                                # Spoolman has no slicer_filament — use the tray's RFID value
                                matching_filament_id = tray_info_idx
                            break

        # Stage 3: live tray.cali_idx fallback. Re-asserts the printer's current
        # selection so the value sticks across the RFID re-read (otherwise some
        # firmwares clear cali_idx back to -1 mid-cycle).
        if matching_cali_idx is None:
            live_cali_idx = tray.get("cali_idx")
            if live_cali_idx is not None and live_cali_idx >= 0:
                matching_cali_idx = live_cali_idx

        if matching_cali_idx is None:
            logger.debug(
                "PA re-apply AMS%d-T%d: no stored or live cali_idx — skipping MQTT",
                ams_id,
                slot_id,
            )
            return

        logger.info(
            "PA re-apply AMS%d-T%d: cali_idx=%d, filament_id=%s",
            ams_id,
            slot_id,
            matching_cali_idx,
            matching_filament_id,
        )

        # NOTE: Do NOT send ams_set_filament_setting here — it tells the firmware
        # "this is a manual config" which destroys the RFID-detected spool state
        # (changes eye icon to pen icon in slicer).
        client.extrusion_cali_sel(
            ams_id=ams_id,
            tray_id=slot_id,
            cali_idx=matching_cali_idx,
            filament_id=matching_filament_id,
            nozzle_diameter=nozzle_diameter,
        )

        # NOTE: Do NOT send extrusion_cali_set here. extrusion_cali_sel already
        # selected the correct profile by cali_idx. Sending extrusion_cali_set with
        # the same cali_idx would MODIFY the existing profile's metadata (extruder_id,
        # nozzle_id, name), corrupting it.

        logger.info(
            "Applied PA profile cali_idx=%d to printer %d AMS%d-T%d",
            matching_cali_idx,
            printer_id,
            ams_id,
            slot_id,
        )
    except Exception as e:
        logger.warning("Failed to apply PA profile after RFID re-read: %s", e)


@router.post("/{printer_id}/ams/load")
async def ams_load(
    printer_id: int,
    tray_id: int = Query(..., description="Tray ID: 0-15 for AMS slots (ams_id*4+slot_id), 254 for external spool"),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Load filament from a specific AMS slot or external spool.

    Tray ID encoding (matches Bambu firmware convention):
    - 0..15: AMS slot, computed as ams_id * 4 + slot_id
    - 254: external spool (single-external printers, or Ext-L on dual-nozzle H2D)
    - 255: Ext-R on dual-nozzle H2D
    """
    if tray_id not in range(16) and tray_id not in (254, 255):
        raise HTTPException(400, "tray_id must be 0..15 (AMS slot), 254 (external / Ext-L), or 255 (Ext-R)")

    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    success = client.ams_load_filament(tray_id)
    if not success:
        raise HTTPException(500, "Failed to send load command")

    if tray_id == 254:
        target = "external spool"
    elif tray_id == 255:
        target = "Ext-R"
    else:
        target = f"AMS {tray_id // 4} slot {tray_id % 4 + 1}"
    return {"success": True, "message": f"Loading filament from {target}"}


@router.post("/{printer_id}/ams/unload")
async def ams_unload(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
):
    """Unload the currently loaded filament."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    client = printer_manager.get_client(printer_id)
    if not client:
        raise HTTPException(400, "Printer not connected")

    success = client.ams_unload_filament()
    if not success:
        raise HTTPException(500, "Failed to send unload command")

    return {"success": True, "message": "Unloading filament"}
